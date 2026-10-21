"""Draw a simplified, plain-English picture of the deployed Model 2 v2 tree.

    python plot_simple_tree.py

Reads ../models/model2_tree_v2.json and saves ../figures/model2_tree_simple.png.
The full tree (figures/model2_decision_tree_v2.png) has more branches; this
picture keeps only the three main questions it asks. The deeper checks (step
rhythm and a few rare cases) are left out to keep it readable.

All the numbers in the picture come from the JSON file, so run this again after
retraining. If retraining changes the shape of the tree, the script stops with
a message instead of drawing a wrong picture.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # just save the figure to a file, don't open a window
import matplotlib.pyplot as plt

import gait_model as gm

PROJECT = Path(__file__).resolve().parent.parent
MODEL_FILE = PROJECT / "models" / "model2_tree_v2.json"
FIGURE_FILE = PROJECT / "figures" / "model2_tree_simple.png"

# Same colors as the guesses on the phone's Live page (unoq_app/assets/style.css)
COLORS = {"Standing": "#4c78a8", "Walking": "#2e9e4a", "Running": "#d64545", "Biking": "#e08a1e"}
QUESTION_COLOR = "#eef2f7"


# ---- 1. Read the thresholds out of the tree ----------------------------
def check(node, feature):
    """Make sure this node asks about the feature we expect, then return its threshold."""
    if node.get("feature") != feature:
        raise SystemExit(f"The tree changed shape: expected a question about {feature}, "
                         f"found {node.get('feature') or node.get('activity')}. "
                         "Update plot_simple_tree.py to match the new tree.")
    return node["threshold"]


def read_thresholds(tree):
    """Each node is {"feature", "threshold", "left", "right"}: left means
    feature <= threshold, right means bigger. Walk to the nodes we draw."""
    bumpy = tree["right"]               # after "the leg is rotating"
    gentle = bumpy["left"]              # 3a: not very bumpy
    smooth_or_jerky = bumpy["right"]    # 3b: very bumpy
    if tree["left"].get("activity") != "Standing":
        raise SystemExit("The tree changed shape: 'not rotating' no longer means Standing.")
    return {
        "spin": check(tree, "gyro_mag_mean"),                         # deg/s
        "bumpy": check(bumpy, "acc_mag_std"),                         # g
        "small_bumps": check(gentle, "acc_mag_std"),                  # g
        "soft_hits": check(gentle["right"], "acc_mag_max"),           # g
        "smooth": check(smooth_or_jerky, "gyro_mag_std"),             # deg/s
    }


# ---- 2. Drawing helpers --------------------------------------------------
def question(ax, x, y, width, title, detail):
    """A rounded box (width in plot units) with the question in bold and a
    smaller line explaining it."""
    ax.text(x, y + 0.17, title, ha="center", va="center", fontsize=13, fontweight="bold")
    ax.text(x, y - 0.25, detail, ha="center", va="center", fontsize=9.5, color="#333")
    ax.add_patch(matplotlib.patches.FancyBboxPatch(
        (x - width / 2, y - 0.55), width, 1.1, boxstyle="round,pad=0.05,rounding_size=0.15",
        facecolor=QUESTION_COLOR, edgecolor="#8a9bb0", linewidth=1.2))


def answer(ax, x, y, activity):
    """A colored box with the final guess, same color as on the Live page."""
    ax.text(x, y, activity, ha="center", va="center", fontsize=14, fontweight="bold", color="white",
            bbox=dict(boxstyle="round,pad=0.5", facecolor=COLORS[activity], edgecolor="none"))


def arrow(ax, start, end, label):
    """Arrow from the bottom of one box to the top of the next, labelled halfway."""
    (x1, y1), (x2, y2) = start, end
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color="#555", linewidth=1.3))
    ax.text((x1 + x2) / 2, (y1 + y2) / 2, label, ha="center", va="center", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#bbb"))


# ---- 3. The picture -------------------------------------------------------
def main():
    t = read_thresholds(gm.load_model(MODEL_FILE)["tree"])

    fig, ax = plt.subplots(figsize=(14, 7.6))
    ax.set_xlim(0, 14)
    ax.set_ylim(0.9, 8.3)
    ax.axis("off")
    ax.set_title("Model 2 in plain words: three questions, asked every half second",
                 fontsize=16, fontweight="bold", pad=12)

    # Where each box sits (x, y)
    q1, q2, q3a, q3b = (7, 7.5), (9.1, 5.6), (4.7, 3.6), (10.9, 3.6)
    standing, walking, running_a, biking, running_b = (2.8, 5.6), (3.2, 1.5), (6.2, 1.5), (9.4, 1.5), (12.4, 1.5)

    question(ax, *q1, 3.6, "1. Is the leg rotating?", f"average spin above {t['spin']:.0f} °/s")
    question(ax, *q2, 4.4, "2. How bumpy is the movement?",
             f"bump size up to {t['bumpy']:.2f} g → 3a, over → 3b")
    question(ax, *q3a, 5.0, "3a. Gentle steps?",
             f"small bumps (up to {t['small_bumps']:.2f} g) and soft hits (up to {t['soft_hits']:.1f} g)")
    question(ax, *q3b, 5.2, "3b. Smooth circles or jerky swings?",
             f"spin speed changes up to {t['smooth']:.0f} °/s = smooth")

    answer(ax, *standing, "Standing")
    answer(ax, *walking, "Walking")
    answer(ax, *running_a, "Running")
    answer(ax, *biking, "Biking")
    answer(ax, *running_b, "Running")

    # Arrows leave from the bottom edge of a question box (y - 0.6)
    # and end at the top of the next box (y + 0.6 for questions, + 0.3 for answers)
    arrow(ax, (q1[0] - 0.8, q1[1] - 0.6), (standing[0] + 0.5, standing[1] + 0.3), "No")
    arrow(ax, (q1[0] + 0.8, q1[1] - 0.6), (q2[0] - 0.4, q2[1] + 0.6), "Yes")
    arrow(ax, (q2[0] - 0.8, q2[1] - 0.6), (q3a[0] + 0.6, q3a[1] + 0.6), f"up to {t['bumpy']:.2f} g")
    arrow(ax, (q2[0] + 0.8, q2[1] - 0.6), (q3b[0] - 0.6, q3b[1] + 0.6), f"over {t['bumpy']:.2f} g")
    arrow(ax, (q3a[0] - 0.7, q3a[1] - 0.6), (walking[0], walking[1] + 0.3), "Yes")
    arrow(ax, (q3a[0] + 0.7, q3a[1] - 0.6), (running_a[0], running_a[1] + 0.3), "No")
    arrow(ax, (q3b[0] - 0.7, q3b[1] - 0.6), (biking[0], biking[1] + 0.3), "Smooth (pedaling)")
    arrow(ax, (q3b[0] + 0.7, q3b[1] - 0.6), (running_b[0], running_b[1] + 0.3), "Jerky (stop-and-go)")

    fig.text(0.5, 0.04, "Simplified from models/model2_tree_v2.json. The full tree also checks "
             "step rhythm and a few rare cases (see model2_decision_tree_v2.png).",
             ha="center", fontsize=9, color="#555")
    fig.savefig(FIGURE_FILE, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved {FIGURE_FILE.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
