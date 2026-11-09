"""
train.py - teach the finger-counting network (model.py) from the photos in
02_data_collection/data/0 ... data/5.

Run:  python train.py
Out:  finger_cnn.pt (the best network), and in this folder:
      loss.png, accuracy.png, confusion_matrix.png, mistakes.png

The steps:
  1. Load every photo and prepare it with hand_crop.to_network_input, the
     same function the live test and the UNO Q use.
  2. Split 80% training / 20% validation, the same share of every class,
     keeping photos taken together in a burst on the same side (see split()).
  3. Train with Adam on cross-entropy loss. Training photos are randomly
     changed a little every time they are shown (augmentation); validation
     photos never are.
  4. After every pass over the training photos (an "epoch"), measure
     validation accuracy. Keep the best network so far; stop when it hasn't
     improved for PATIENCE epochs.
  5. Draw the plots and the confusion matrix from the best network.
"""
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
import matplotlib
matplotlib.use("Agg")                        # draw straight to files, no window needed
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "02_data_collection"))   # so hand_crop.py can be imported
import hand_crop as hc                       # noqa: E402  (the shared photo preparation)
from model import CLASSES, FingerCNN, count_dead_filters, count_parameters    # noqa: E402

DATA_DIR = HERE.parent / "02_data_collection" / "data"
MODEL_PATH = HERE / "finger_cnn.pt"

# ---- Settings ----------------------------------------------------------------
SEED = 0              # fixes the split, the starting weights and the augmentation, so a rerun gives the same result
VAL_BLOCKS = 2        # each class's photos (in time order) are cut into 10 blocks; 2 of them = 20% validation
N_BLOCKS = 10
BATCH_SIZE = 32       # photos per weight update: small enough for frequent updates, big enough to be steady
LEARNING_RATE = 1e-3  # Adam's usual step size. Also tried: 3e-4 (slower and no steadier, 75%) and
                      # halving the step whenever validation stalled (it shrank too early, 72%).
MAX_EPOCHS = 150      # a ceiling; early stopping normally ends training before this
PATIENCE = 30         # stop after this many epochs without a better validation result. Validation
                      # accuracy jumps a lot from epoch to epoch (see the README), so this waits long
                      # enough not to stop on an unlucky dip.

# Augmentation strengths (training photos only)
MAX_ROTATION = 15.0   # degrees, either way
MAX_SHIFT = 0.08      # up to 8% of the photo's width/height (about 10 pixels)
BRIGHTNESS = 0.2      # brightness multiplied by a random factor between 0.8 and 1.2


# ---- 1. Loading --------------------------------------------------------------

def photo_time(path):
    """The date-time stamp in a file name like mohammed_2_20261108-133424-117.png."""
    stamp = re.search(r"_(\d{8}-\d{6}-\d{3})\.png$", path.name).group(1)
    return datetime.strptime(stamp, "%Y%m%d-%H%M%S-%f")


def load_photos():
    """All photos as a list per class, each list in the order the photos were taken."""
    per_class = []
    for c in CLASSES:
        files = sorted((DATA_DIR / c).glob("*.png"), key=photo_time)
        if not files:
            sys.exit(f"No photos in {DATA_DIR / c}. Take some with capture.py first.")
        photos = []
        for f in files:
            img = cv2.imread(str(f))                      # BGR, the same order capture.py saved
            hc.to_network_input(img)                      # only to check the size; raises if wrong
            photos.append((f, img))
        per_class.append(photos)
    return per_class


# ---- 2. Splitting ------------------------------------------------------------

SESSION_GAP_MIN = 30   # a pause longer than this (minutes) between two photos starts a new capture session


def sessions(photos):
    """Cut one class's photos (in time order) into capture sessions, e.g. daylight and evening."""
    groups = [[photos[0]]]
    for prev, cur in zip(photos, photos[1:]):
        gap = (photo_time(cur[0]) - photo_time(prev[0])).total_seconds() / 60
        if gap > SESSION_GAP_MIN:
            groups.append([])
        groups[-1].append(cur)
    return groups


def split(per_class, rng):
    """80% training / 20% validation, balanced, and fair.

    Balanced: the same share (2 blocks of 10) is taken from every class AND
    from every capture session, so validation has about 20% of each count in
    daylight and 20% in evening light. (Without this, the 2 random blocks of
    a class could both land in one session, and the evening shadows might
    never be tested.)

    Fair: photos were taken in bursts (holding a key saves ~5 per second), so
    neighbors in time are near copies. If photos were picked one by one at
    random, almost every validation photo would have a near twin in training,
    and validation would test memory instead of understanding. So each
    session of each class is cut, in time order, into 10 blocks of
    consecutive photos, and whole blocks go to one side or the other. (Only
    the photos at a block's edge still have a near twin across the line.)

    The first session is split for every class before the second, so the
    daylight validation photos are exactly the ones used before the evening
    photos were added, and old and new networks can be compared on them.
    """
    train, val = [], []
    per_session = [sessions(photos) for photos in per_class]
    for s in range(max(len(g) for g in per_session)):
        for label, groups in enumerate(per_session):
            if s >= len(groups):
                continue
            photos = groups[s]
            blocks = np.array_split(np.arange(len(photos)), N_BLOCKS)
            val_ids = set(rng.choice(N_BLOCKS, size=VAL_BLOCKS, replace=False).tolist())
            for b, idx in enumerate(blocks):
                for i in idx:
                    (val if b in val_ids else train).append((photos[i][0], photos[i][1], label))
    return train, val


def session_labels(per_class):
    """Which capture session each photo came from, as {photo path: "session 2 (from 16:41)"}.

    Used to report validation accuracy per session (daylight, evening, ...),
    so a new session can be judged on its own instead of hiding in the total.
    """
    groups = [sessions(photos) for photos in per_class]
    n = max(len(g) for g in groups)
    starts = [min(photo_time(g[s][0][0]) for g in groups if s < len(g)) for s in range(n)]
    return {path: f"session {s + 1} (from {starts[s]:%H:%M})"
            for g in groups for s, sess in enumerate(g) for path, _ in sess}


def report_by_session(items, guess, labels):
    """Validation accuracy and mistakes for each capture session separately."""
    print("\nBy capture session (validation photos):")
    for name in sorted(set(labels[p] for p, _, _ in items)):
        idx = [i for i, (p, _, _) in enumerate(items) if labels[p] == name]
        right = sum(int(guess[i]) == items[i][2] for i in idx)
        wrong = {}
        for i in idx:
            if int(guess[i]) != items[i][2]:
                key = f"{items[i][2]}->{int(guess[i])}"
                wrong[key] = wrong.get(key, 0) + 1
        print(f"  {name}: {right / len(idx):6.1%} ({right} of {len(idx)})"
              + (f"  mistakes: {', '.join(f'{k} x{v}' for k, v in sorted(wrong.items()))}" if wrong else ""))


# ---- 3. Augmentation (training photos only) ----------------------------------

def augment(img, rng):
    """Return a slightly changed copy of a 128x128 photo. A new random change every time.

    Why each change helps (the network should learn "how many fingers", not
    "exactly these pixels"):
      * Rotation (+-15 deg): a hand is never held at exactly the same angle twice.
      * Shift (+-8%): the hand won't sit in exactly the same spot in the box.
      * Brightness (x0.8 to x1.2): room light changes (daylight, lamps, a shadow).
      * Horizontal flip (half the time): a mirrored right hand looks like a left
        hand, so the network also learns left hands without anyone recording them.
    The edges uncovered by rotating or shifting are filled by mirroring the
    nearby pixels (BORDER_REFLECT_101), so they look like more red tape and
    wood instead of black corners the real camera never shows.
    """
    s = hc.IMAGE_SIZE
    angle = rng.uniform(-MAX_ROTATION, MAX_ROTATION)
    tx, ty = rng.uniform(-MAX_SHIFT, MAX_SHIFT, size=2) * s
    m = cv2.getRotationMatrix2D((s / 2, s / 2), angle, 1.0)   # rotate about the center
    m[:, 2] += (tx, ty)                                        # then shift
    out = cv2.warpAffine(img, m, (s, s), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    factor = rng.uniform(1 - BRIGHTNESS, 1 + BRIGHTNESS)
    out = np.clip(out.astype(np.float32) * factor, 0, 255).astype(np.uint8)
    if rng.random() < 0.5:
        out = out[:, ::-1]                                     # mirror left <-> right
    return np.ascontiguousarray(out)


def to_batch(images):
    """A list of 128x128 BGR photos -> one PyTorch tensor (N, 3, 128, 128), via the shared hand_crop step."""
    return torch.from_numpy(np.stack([hc.to_network_input(im) for im in images]))


# ---- 4. Training -------------------------------------------------------------

def evaluate(model, items, loss_fn):
    """Loss, accuracy and every guess on photos used AS THEY ARE (no augmentation)."""
    model.eval()                                  # guessing mode
    with torch.no_grad():                         # no gradients needed just to measure
        x = to_batch([im for _, im, _ in items])
        y = torch.tensor([lab for _, _, lab in items])
        scores = model(x)
        loss = loss_fn(scores, y).item()
        guesses = scores.argmax(1)
    return loss, (guesses == y).float().mean().item(), guesses.numpy(), y.numpy()


def train(train_items, val_items, rng):
    torch.manual_seed(SEED)                       # same random starting weights every run
    model = FingerCNN()
    print(f"Network: {count_parameters(model):,} parameters "
          f"(about {count_parameters(model) * 4 / 1024:.0f} KB as 32-bit numbers)")
    loss_fn = nn.CrossEntropyLoss()               # cross-entropy: punishes a confident wrong guess the most
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)   # Adam: gradient descent that adapts each weight's step size

    history = {k: [] for k in ("train_loss", "train_acc", "val_loss", "val_acc")}
    best = None                                   # (val accuracy, -val loss, epoch)
    waited = 0
    for epoch in range(1, MAX_EPOCHS + 1):
        t0 = time.time()
        model.train()                             # learning mode
        order = rng.permutation(len(train_items))  # a new shuffled order every epoch
        total_loss, correct = 0.0, 0
        for start in range(0, len(order), BATCH_SIZE):
            batch = [train_items[i] for i in order[start:start + BATCH_SIZE]]
            x = to_batch([augment(im, rng) for _, im, _ in batch])   # fresh random changes each time
            y = torch.tensor([lab for _, _, lab in batch])
            scores = model(x)
            loss = loss_fn(scores, y)
            optimizer.zero_grad()                 # clear the last step's gradients
            loss.backward()                       # chain rule through every layer (as in the warm-up, but automatic)
            optimizer.step()                      # Adam nudges every weight downhill
            total_loss += loss.item() * len(batch)
            correct += (scores.argmax(1) == y).sum().item()
        train_loss, train_acc = total_loss / len(order), correct / len(order)
        val_loss, val_acc, _, _ = evaluate(model, val_items, loss_fn)
        for k, v in zip(history, (train_loss, train_acc, val_loss, val_acc)):
            history[k].append(v)

        # "Better" = higher validation accuracy; on a tie, lower validation loss
        # (the network is right on the same photos but more sure of it).
        score = (val_acc, -val_loss)
        mark = ""
        if best is None or score > best[:2]:
            best = (val_acc, -val_loss, epoch)
            waited = 0
            torch.save({
                "state_dict": model.state_dict(),
                "classes": CLASSES,
                "image_size": hc.IMAGE_SIZE,
                "frame_size": [hc.FRAME_W, hc.FRAME_H],
                "epoch": epoch,
                "val_accuracy": val_acc,
                "val_loss": val_loss,
                "seed": SEED,
                "val_files": [f"{lab}/{p.name}" for p, _, lab in val_items],
            }, MODEL_PATH)
            mark = "  <- best so far, saved"
        else:
            waited += 1
        print(f"epoch {epoch:3d}  train loss {train_loss:.3f} acc {train_acc:6.1%}  |  "
              f"val loss {val_loss:.3f} acc {val_acc:6.1%}  ({time.time() - t0:.1f}s){mark}")
        if waited >= PATIENCE:
            print(f"No better validation result for {PATIENCE} epochs: stopping.")
            break
    return history, best[2]


# ---- 5. Plots ----------------------------------------------------------------

def plot_history(history, best_epoch):
    epochs = range(1, len(history["train_loss"]) + 1)
    for key, name, fname in (("loss", "loss (cross-entropy)", "loss.png"), ("acc", "accuracy", "accuracy.png")):
        plt.figure(figsize=(6.8, 4.2))
        plt.plot(epochs, history[f"train_{key}"], color="#1f6feb", lw=2, label="training (augmented photos)")
        plt.plot(epochs, history[f"val_{key}"], color="#d1242f", lw=2, label="validation (unchanged photos)")
        plt.axvline(best_epoch, color="#8c959f", ls="--", lw=1.2, label=f"best epoch ({best_epoch}), saved")
        if key == "acc":
            plt.ylim(0, 1.02)
        plt.xlabel("epoch")
        plt.ylabel(name)
        plt.title(f"Finger counter: {name} vs epoch")
        plt.grid(alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig(HERE / fname, dpi=150)
        plt.close()


def plot_confusion(true, guess):
    """6x6 table: row = the real count, column = the network's guess. The diagonal is correct."""
    cm = np.zeros((len(CLASSES), len(CLASSES)), int)
    for t, g in zip(true, guess):
        cm[t, g] += 1
    plt.figure(figsize=(5.4, 4.8))
    plt.imshow(cm, cmap="Blues")
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            plt.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=12)
    plt.xticks(range(len(CLASSES)), CLASSES)
    plt.yticks(range(len(CLASSES)), CLASSES)
    plt.xlabel("network's guess")
    plt.ylabel("real number of fingers")
    plt.title("Validation photos: which counts get mixed up")
    plt.tight_layout()
    plt.savefig(HERE / "confusion_matrix.png", dpi=150)
    plt.close()
    return cm


def save_mistakes(items, guess):
    """A strip of the validation photos the network got wrong, labeled 'real -> guess'."""
    wrong = [(im, lab, g) for (_, im, lab), g in zip(items, guess) if lab != g]
    if not wrong:
        return 0
    tiles = []
    for im, lab, g in wrong[:12]:
        t = cv2.copyMakeBorder(im, 24, 2, 2, 2, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(t, f"real {lab} -> {g}", (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1)
        tiles.append(t)
    cv2.imwrite(str(HERE / "mistakes.png"), np.hstack(tiles))
    return len(wrong)


def main():
    rng = np.random.default_rng(SEED)
    per_class = load_photos()
    print("Photos per class:", {c: len(p) for c, p in zip(CLASSES, per_class)})
    train_items, val_items = split(per_class, rng)
    print(f"Split: {len(train_items)} training, {len(val_items)} validation "
          f"({ {c: sum(1 for *_, l in val_items if l == i) for i, c in enumerate(CLASSES)} } per class)")

    history, best_epoch = train(train_items, val_items, rng)
    plot_history(history, best_epoch)

    # Judge the BEST saved network (not the last one) on the validation photos
    model = FingerCNN()
    model.load_state_dict(torch.load(MODEL_PATH, weights_only=False)["state_dict"])
    loss, acc, guess, true = evaluate(model, val_items, nn.CrossEntropyLoss())
    cm = plot_confusion(true, guess)
    n_wrong = save_mistakes(val_items, guess)
    print(f"\nBest network: epoch {best_epoch}, validation accuracy {acc:.1%} "
          f"({len(val_items) - n_wrong} of {len(val_items)}), loss {loss:.3f}")
    # Honesty check: the best epoch is partly luck, because validation accuracy jumps
    # between epochs. The average over the last 10 epochs is a fairer "typical" score.
    last = history["val_acc"][-10:]
    print(f"Typical validation accuracy (last {len(last)} epochs): {np.mean(last):.1%} "
          f"(lowest {min(last):.1%}, highest {max(last):.1%})")
    # Filters that never switch on for any photo have stopped learning (see model.py)
    dead = count_dead_filters(model, to_batch([im for _, im, _ in train_items + val_items]))
    print(f"Dead filters (never switch on for any photo), layer 1/2/3: {dead[0]}/8, {dead[1]}/16, {dead[2]}/32")
    report_by_session(val_items, guess, session_labels(per_class))
    for i, c in enumerate(CLASSES):
        print(f"  {c} fingers: {cm[i, i]} of {cm[i].sum()} right"
              + "".join(f", {cm[i, j]} called {CLASSES[j]}" for j in range(len(CLASSES)) if j != i and cm[i, j]))
    print("Saved finger_cnn.pt, loss.png, accuracy.png, confusion_matrix.png"
          + (", mistakes.png" if n_wrong else ""))


if __name__ == "__main__":
    main()
