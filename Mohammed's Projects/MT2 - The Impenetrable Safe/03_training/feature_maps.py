"""
feature_maps.py - pictures of what each convolution layer "sees", for the stop-action movie.

Run:  python feature_maps.py      (after train.py)
Out:  feature_maps/class<N>_<step>_<name>.png, five frames per class, all the
      same size so they can go straight into a movie in order:
        1_photo   the photo the network is given
        2_conv1   layer 1: 8 feature maps, 128x128 each
        3_conv2   layer 2: 16 feature maps, 64x64 each
        4_conv3   layer 3: 32 feature maps, 32x32 each
        5_guess   the six confidences and the final guess
      plus feature_maps/overview.png (one row per class) for the README.

What a feature map is: each filter is a small pattern detector that slides
over the picture. Its feature map is a grayscale picture of WHERE it found its
pattern: bright = "found it strongly here", dark = "not here". Layer 1 maps
still look like the photo (edges, skin, the red tape); each later layer is
smaller (pooling halves it) and more abstract (fingertips, finger edges,
gaps between fingers), which is how the network goes from pixels to a count.

Which photo: one VALIDATION photo per class (never used for learning), the
one the network is most sure about, so the pictures show it working as intended.

Each map is brightened to its own strongest point so faint maps are still
visible; compare shapes within a map, not brightness between maps.
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "02_data_collection"))
import hand_crop as hc                      # noqa: E402
from model import CLASSES, load_trained    # noqa: E402

DATA_DIR = HERE.parent / "02_data_collection" / "data"
OUT_DIR = HERE / "feature_maps"
FRAME_SIZE = (16, 9)     # inches at 100 dpi = 1600x900 pixels, a movie-friendly 16:9 frame
LAYER_NOTES = [
    "Layer 1: 8 filters, each 128x128. Simple things: edges, skin vs. wood, the red tape.",
    "Layer 2: 16 filters, each 64x64. Combinations: finger edges, fingertips.",
    "Layer 3: 32 filters, each 32x32. Bigger parts: whole fingers, the gaps between them.",
]


def pick_examples(model, val_files):
    """For each class, the validation photo the network is most confident (and right) about."""
    picks = {}
    for rel in val_files:
        label = int(rel.split("/")[0])
        img = cv2.imread(str(DATA_DIR / rel))
        x = torch.from_numpy(hc.to_network_input(img)).unsqueeze(0)
        with torch.no_grad():
            p = torch.softmax(model(x), 1)[0]
        if p.argmax().item() == label and p[label] > picks.get(label, (None, -1))[1]:
            picks[label] = (img, p[label].item())
    return {lab: img for lab, (img, _) in picks.items()}


def rgb(img):
    """OpenCV stores blue-green-red; matplotlib draws red-green-blue."""
    return img[:, :, ::-1]


def new_frame(img, title):
    """A blank 1600x900 frame with the photo on the left and a title on top."""
    fig = plt.figure(figsize=FRAME_SIZE, dpi=100)
    fig.suptitle(title, fontsize=22, y=0.97)
    ax = fig.add_axes([0.02, 0.25, 0.25, 0.5])    # the photo, always shown for context
    ax.imshow(rgb(img))
    ax.set_title("the photo", fontsize=14)
    ax.axis("off")
    return fig


def save_layer_frame(img, maps, layer, label, path):
    """One frame: the photo plus every feature map of one layer, in a grid."""
    n = maps.shape[0]
    cols = {8: 4, 16: 4, 32: 8}[n]
    rows = n // cols
    fig = new_frame(img, f"Class {label}: what layer {layer + 1} sees")
    fig.text(0.5, 0.03, LAYER_NOTES[layer], ha="center", fontsize=15)
    left, width, top, height = 0.31, 0.67, 0.88, 0.78
    for k in range(n):
        r, c = divmod(k, cols)
        ax = fig.add_axes([left + c * width / cols, top - (r + 1) * height / rows,
                           width / cols * 0.94, height / rows * 0.94])
        m = maps[k]
        ax.imshow(m / m.max() if m.max() > 0 else m, cmap="magma", vmin=0, vmax=1)
        ax.axis("off")
    fig.savefig(path)
    plt.close(fig)


def save_guess_frame(img, probs, label, path):
    """Last frame: the six confidences as bars and the final answer."""
    best = int(probs.argmax())
    fig = new_frame(img, f"Class {label}: the network's answer is {CLASSES[best]} ({probs[best]:.0%} sure)")
    ax = fig.add_axes([0.36, 0.18, 0.58, 0.65])
    colors = ["#1a7f37" if i == best else "#8c959f" for i in range(len(CLASSES))]
    ax.bar(CLASSES, probs, color=colors)
    ax.set_ylim(0, 1)
    ax.set_xlabel("number of fingers", fontsize=15)
    ax.set_ylabel("confidence", fontsize=15)
    ax.tick_params(labelsize=13)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.5, 0.03, "The final layer weighs all 8,192 layer-3 numbers into six scores; "
             "softmax turns them into confidences that add up to 100%.", ha="center", fontsize=15)
    fig.savefig(path)
    plt.close(fig)


def main():
    model, info = load_trained(HERE / "finger_cnn.pt")
    OUT_DIR.mkdir(exist_ok=True)
    examples = pick_examples(model, info["val_files"])
    overview = []
    for label in range(len(CLASSES)):
        if label not in examples:
            print(f"class {label}: no correctly guessed validation photo, skipped")
            continue
        img = examples[label]
        x = torch.from_numpy(hc.to_network_input(img)).unsqueeze(0)
        with torch.no_grad():
            scores, maps = model.forward_with_maps(x)
        probs = torch.softmax(scores, 1)[0].numpy()
        maps = [m[0].numpy() for m in maps]                  # drop the batch dimension
        stem = OUT_DIR / f"class{label}"

        fig = new_frame(img, f"Class {label}: the photo goes in")
        fig.text(0.5, 0.03, "128 x 128 pixels, 3 colors = 49,152 numbers", ha="center", fontsize=15)
        fig.savefig(f"{stem}_1_photo.png")
        plt.close(fig)
        for layer, m in enumerate(maps):
            save_layer_frame(img, m, layer, label, f"{stem}_{layer + 2}_conv{layer + 1}.png")
        save_guess_frame(img, probs, label, f"{stem}_5_guess.png")
        overview.append((label, img, maps, probs))
        print(f"class {label}: guessed {CLASSES[probs.argmax()]} ({probs.max():.0%}), 5 frames saved")

    # Overview for the README: per class, the photo and the strongest map of each layer
    fig, axes = plt.subplots(len(overview), 4, figsize=(8, 2.1 * len(overview)))
    for row, (label, img, maps, probs) in zip(axes, overview):
        row[0].imshow(rgb(img))
        row[0].set_ylabel(f"class {label}", fontsize=12)
        for ax, m, name in zip(row[1:], maps, ("layer 1", "layer 2", "layer 3")):
            k = int(m.reshape(len(m), -1).mean(1).argmax())  # the most active filter of this layer
            ax.imshow(m[k] / max(m[k].max(), 1e-6), cmap="magma", vmin=0, vmax=1)
            ax.set_title(f"{name}, filter {k + 1}", fontsize=10)   # each row shows its own most active filter
        for ax in row:
            ax.set_xticks([])
            ax.set_yticks([])
    axes[0][0].set_title("photo", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "overview.png", dpi=120)
    plt.close(fig)
    print(f"Saved {OUT_DIR.name}/ (5 frames per class + overview.png)")


if __name__ == "__main__":
    main()
