"""Practice run for HW7: a small PyTorch neural net that recognizes the
activity (Standing, Walking, Running, Biking) from the HW6 recordings.

    python practice_classifier.py

This is a warm-up before the real HW7 data exists. It does the same kind of
work the step counter will need later (cut IMU data into clips, turn each
clip into numbers, train a net in PyTorch, test it fairly) on data we
already have.

1. Loads every CSV in "Gait Identifier/data/raw" (the HW6 recordings).
2. Trims 2 s off both ends of each recording and cuts the rest into 2 s clips.
3. Describes each clip with 18 numbers: the average, spread and peak of each
   of the 6 IMU channels.
4. Sets aside one whole recording per activity for testing. Clips from the
   same recording look almost identical, so if some clips of a recording were
   used for training and others for testing, the test would be too easy.
5. Trains a net with 18 inputs -> 16 neurons -> 16 neurons -> 4 activities.
6. Saves a plot of the loss going down to ../media and prints the test
   accuracy and a confusion matrix.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # just save the figure to a file, don't open a window
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn

# ---- Settings ------------------------------------------------------------
PROJECT = Path(__file__).resolve().parent.parent           # .../How Many Steps
DATA_DIR = PROJECT.parent / "Gait Identifier" / "data" / "raw"
MEDIA_DIR = PROJECT / "media"

SAMPLE_RATE_HZ = 100     # the HW6 sketch read the MPU-6050 100 times a second
TRIM_SECONDS = 2         # the start and end of a recording are pressing Start/Stop
                         # on the phone, not the activity itself, so drop them
CLIP_SECONDS = 2         # one clip = 2 s = 200 samples
CLIP_SAMPLES = CLIP_SECONDS * SAMPLE_RATE_HZ

CHANNELS = ["ax", "ay", "az", "gx", "gy", "gz"]  # accel in g, gyro in deg/s
STATS = ["avg", "spread", "peak"]                # the 3 numbers per channel
ACTIVITIES = ["Standing", "Walking", "Running", "Biking"]  # output order of the net

HIDDEN = 16              # neurons in each of the two hidden layers
EPOCHS = 300             # how many times the net sees the whole training set
LEARNING_RATE = 0.01     # how big a step the optimizer takes each time
SEED = 0                 # fixes the random choices so every run gives the same result


# ---- 1. Load the recordings ----------------------------------------------
def load_recording(path):
    """Read one CSV. Returns (data, activity): data has one row per sample and
    one column per channel (ax, ay, az, gx, gy, gz)."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    data = np.array([[float(row[c]) for c in CHANNELS] for row in rows])
    return data, rows[0]["activity"]


# ---- 2. Cut a recording into clips ---------------------------------------
def make_clips(data):
    """Trim the ends, then cut the rest into back-to-back 2 s clips (no
    overlap). Any leftover bit shorter than 2 s at the end is dropped.
    Returns an array shaped (number of clips, 200 samples, 6 channels)."""
    trim = TRIM_SECONDS * SAMPLE_RATE_HZ
    data = data[trim:len(data) - trim]
    n_clips = len(data) // CLIP_SAMPLES
    return data[:n_clips * CLIP_SAMPLES].reshape(n_clips, CLIP_SAMPLES, len(CHANNELS))


# ---- 3. Describe a clip with 18 numbers ----------------------------------
def clip_features(clip):
    """For each channel: average (where the signal sits, e.g. how gravity
    falls on that axis), spread (standard deviation: how much it moves) and
    peak (largest absolute value: the hardest jolt or fastest turn).
    6 channels x 3 numbers = 18 inputs for the net."""
    return np.concatenate([clip.mean(axis=0), clip.std(axis=0), np.abs(clip).max(axis=0)])


def feature_names():
    """Names in the same order as clip_features(), e.g. "ax_avg"."""
    return [f"{c}_{s}" for s in STATS for c in CHANNELS]


def load_dataset():
    """Returns X (one row of 18 features per clip), y (activity number per
    clip), the recording each clip came from, and the list of file names."""
    files = sorted(DATA_DIR.glob("*.csv"))
    X, y, recording_ids = [], [], []
    for rec_id, path in enumerate(files):
        data, activity = load_recording(path)
        for clip in make_clips(data):
            X.append(clip_features(clip))
            y.append(ACTIVITIES.index(activity))
            recording_ids.append(rec_id)
    return np.array(X), np.array(y), np.array(recording_ids), files


# ---- 4. Keep whole recordings aside for testing ---------------------------
def pick_test_recordings(y, recording_ids, rng):
    """Pick one recording of each activity at random for the test set. Every
    clip of a chosen recording goes to testing and none of it to training."""
    test_recs = []
    for label in range(len(ACTIVITIES)):
        recs_of_activity = np.unique(recording_ids[y == label])
        test_recs.append(rng.choice(recs_of_activity))
    return np.isin(recording_ids, test_recs), test_recs


# ---- 5. The neural net ---------------------------------------------------
def make_net(n_inputs):
    """18 inputs -> 16 neurons -> 16 neurons -> 4 outputs.
    Each nn.Linear layer multiplies its inputs by learned weights and adds a
    learned bias. ReLU (keep positives, turn negatives into 0) between the
    layers lets the net learn curved boundaries instead of only straight ones.
    The 4 outputs are scores, one per activity; the biggest score is the
    net's guess. No softmax at the end, because CrossEntropyLoss below
    applies it itself."""
    return nn.Sequential(
        nn.Linear(n_inputs, HIDDEN),
        nn.ReLU(),
        nn.Linear(HIDDEN, HIDDEN),
        nn.ReLU(),
        nn.Linear(HIDDEN, len(ACTIVITIES)),
    )


def train(net, X_train, y_train, X_test, y_test):
    """Train the net and record the loss on both sets after every epoch.
    The test loss is only recorded for the plot: it never changes the
    weights, so the test recordings stay unseen by the training."""
    # Walking has many more clips than Standing, so without weights the net
    # could score well by mostly guessing Walking. Weighting each activity by
    # 1 / (its number of clips) makes every activity count equally.
    counts = torch.bincount(y_train, minlength=len(ACTIVITIES)).float()
    loss_fn = nn.CrossEntropyLoss(weight=counts.sum() / (len(ACTIVITIES) * counts))
    # Adam is the usual optimizer: a gradient-descent variant that adjusts its
    # step size for each weight on its own.
    optimizer = torch.optim.Adam(net.parameters(), lr=LEARNING_RATE)

    train_losses, test_losses = [], []
    for _ in range(EPOCHS):
        # One training step on all training clips at once (the set is small).
        net.train()
        optimizer.zero_grad()                       # clear last step's gradients
        loss = loss_fn(net(X_train), y_train)       # how wrong is the net right now?
        loss.backward()                             # which way should each weight move?
        optimizer.step()                            # move the weights a little that way
        train_losses.append(loss.item())

        net.eval()
        with torch.no_grad():                       # just measuring, no learning
            test_losses.append(loss_fn(net(X_test), y_test).item())
    return train_losses, test_losses


# ---- 6. Results ------------------------------------------------------------
def save_loss_plot(train_losses, test_losses):
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(train_losses, label="training clips")
    ax.plot(test_losses, label="test recordings (held out)")
    ax.set_xlabel("Epoch (one pass over the training clips)")
    ax.set_ylabel("Loss (cross-entropy, lower is better)")
    ax.set_title("Practice net on HW6 data: 18 -> 16 -> 16 -> 4")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = MEDIA_DIR / "practice_loss.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def print_confusion_matrix(y_true, y_pred):
    """Rows are the true activity, columns what the net guessed. Everything
    on the diagonal is correct; anything off it is a mix-up."""
    matrix = np.zeros((len(ACTIVITIES), len(ACTIVITIES)), dtype=int)
    for t, p in zip(y_true, y_pred):
        matrix[t, p] += 1
    width = max(len(a) for a in ACTIVITIES) + 2
    print("\nConfusion matrix (rows = true, columns = predicted):")
    print(" " * width + "".join(f"{a:>{width}}" for a in ACTIVITIES))
    for activity, row in zip(ACTIVITIES, matrix):
        print(f"{activity:<{width}}" + "".join(f"{n:>{width}}" for n in row))


def main():
    # Same seed for numpy (test split) and torch (starting weights), so the
    # run is repeatable.
    rng = np.random.default_rng(SEED)
    torch.manual_seed(SEED)

    X, y, recording_ids, files = load_dataset()
    print(f"Loaded {len(files)} recordings -> {len(X)} clips of {CLIP_SECONDS} s, "
          f"{X.shape[1]} features each")

    is_test, test_recs = pick_test_recordings(y, recording_ids, rng)
    print(f"Training: {np.sum(~is_test)} clips from {len(files) - len(test_recs)} recordings")
    print(f"Testing:  {np.sum(is_test)} clips from these held-out recordings:")
    for rec in test_recs:
        print(f"  {files[rec].name}  ({np.sum(recording_ids == rec)} clips)")

    # Rescale every feature to average 0 and spread 1. Raw features range from
    # about 0.01 g to hundreds of deg/s, and a net learns badly when its inputs
    # are on such different scales. The scaling is measured on the training
    # clips only, because the test set must stay unseen.
    mean = X[~is_test].mean(axis=0)
    std = X[~is_test].std(axis=0) + 1e-8   # + tiny number avoids dividing by 0
    X_scaled = (X - mean) / std

    # PyTorch works on tensors: float32 for inputs, whole numbers for labels.
    X_train = torch.tensor(X_scaled[~is_test], dtype=torch.float32)
    y_train = torch.tensor(y[~is_test], dtype=torch.long)
    X_test = torch.tensor(X_scaled[is_test], dtype=torch.float32)
    y_test = torch.tensor(y[is_test], dtype=torch.long)

    net = make_net(X.shape[1])
    train_losses, test_losses = train(net, X_train, y_train, X_test, y_test)
    print(f"\nLoss: {train_losses[0]:.3f} -> {train_losses[-1]:.3f} (training), "
          f"{test_losses[0]:.3f} -> {test_losses[-1]:.3f} (test)")
    print(f"Saved {save_loss_plot(train_losses, test_losses).relative_to(PROJECT.parent)}")

    # Test: the net's guess for each clip is the activity with the biggest score.
    net.eval()
    with torch.no_grad():
        y_pred = net(X_test).argmax(dim=1).numpy()
    y_true = y_test.numpy()
    print(f"\nTest accuracy: {np.mean(y_pred == y_true):.1%} ({np.sum(y_pred == y_true)}/{len(y_true)} clips)")
    print_confusion_matrix(y_true, y_pred)


if __name__ == "__main__":
    main()
