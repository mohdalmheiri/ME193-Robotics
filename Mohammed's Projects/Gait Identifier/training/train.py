"""Train and test the two gait models on the laptop.

    python train.py

1. Loads every CSV in ../data/raw and cuts it into 2 s windows (see gait_model.py).
2. Model 1 (one direction): the peak |acceleration| on ONE axis, split into
   activities by up to 3 thresholds. Tries ax, ay and az and keeps the best.
3. Model 2 (all IMU outputs): 30 features (mean, std, min, max, dominant
   frequency for each of the 6 channels) fed to a decision tree, max depth 4.
4. Tests both with leave-one-recording-out: train on 11 recordings, test on the
   one left out, repeat for all 12. Windows from the same recording overlap and
   look alike, so testing on random windows would be cheating.
5. Saves figures to ../figures and the trained models (as JSON) to ../models.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # just save figures to files, don't open windows
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, confusion_matrix
from sklearn.tree import DecisionTreeClassifier, plot_tree

import gait_model as gm

PROJECT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT / "data" / "raw"
FIGURES_DIR = PROJECT / "figures"
MODELS_DIR = PROJECT / "models"

# Colors for the 4 activities (same order as gm.ACTIVITIES) in every figure
COLORS = ["#4C78A8", "#59A14F", "#E15759", "#F28E2B"]


# ---- 1. Load the data ---------------------------------------------------
def load_dataset():
    """Returns one list entry per window: the window itself, its activity, and
    which recording it came from (needed to hold out whole recordings)."""
    windows, labels, recording_ids = [], [], []
    files = sorted(DATA_DIR.glob("*.csv"))
    for rec_id, path in enumerate(files):
        data, activity = gm.load_recording(path)
        for window in gm.make_windows(data):
            windows.append(window)
            labels.append(activity)
            recording_ids.append(rec_id)
    print(f"Loaded {len(files)} recordings -> {len(windows)} windows of "
          f"{gm.WINDOW_SAMPLES / gm.SAMPLE_RATE_HZ:.0f} s")
    for activity in gm.ACTIVITIES:
        n_rec = len({r for r, a in zip(recording_ids, labels) if a == activity})
        print(f"  {activity:9s} {n_rec} recordings, {labels.count(activity)} windows")
    return windows, np.array(labels), np.array(recording_ids)


# ---- The two models -----------------------------------------------------
def new_model1():
    # A depth-2 tree on a single number = at most 3 thresholds (4 bands).
    # class_weight="balanced" so the activities with fewer windows
    # (Running, Biking) count as much as the others.
    return DecisionTreeClassifier(max_depth=2, class_weight="balanced", random_state=0)


def new_model2():
    return DecisionTreeClassifier(max_depth=4, class_weight="balanced", random_state=0)


# ---- 4. Leave-one-recording-out testing ---------------------------------
def leave_one_recording_out(make_model, X, y, recording_ids):
    """Train on all recordings but one, predict the one left out, repeat for
    each recording. Returns a prediction for every window."""
    predictions = np.empty(len(y), dtype=object)
    for rec in np.unique(recording_ids):
        test = recording_ids == rec
        model = make_model().fit(X[~test], y[~test])
        predictions[test] = model.predict(X[test])
    return predictions


# ---- 6. Turning trained trees into simple JSON --------------------------
def tree_to_bands(tree):
    """Model 1 is a tree on one number, so it really just cuts the number line
    into bands. Read the cut points out of the tree and the activity for each
    band, merging neighbouring bands that predict the same activity."""
    cuts = sorted(t for t, f in zip(tree.tree_.threshold, tree.tree_.feature) if f >= 0)
    # Ask the tree about one point inside each band
    edges = [cuts[0] - 1] + cuts + [cuts[-1] + 1]
    middles = [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]
    middles[0], middles[-1] = cuts[0] - 1e-6, cuts[-1] + 1e-6
    classes = list(tree.predict(np.array(middles).reshape(-1, 1)))
    # Drop a cut if the bands on both sides give the same answer
    thresholds, kept = [], [classes[0]]
    for cut, activity in zip(cuts, classes[1:]):
        if activity != kept[-1]:
            thresholds.append(float(cut))
            kept.append(activity)
    return thresholds, kept


def tree_to_dict(tree, names, node=0):
    """Model 2: write the tree as nested questions. A leaf just says the activity."""
    t = tree.tree_
    if t.feature[node] < 0:  # leaf
        return {"activity": str(tree.classes_[np.argmax(t.value[node])])}
    return {
        "feature": names[t.feature[node]],
        "threshold": float(t.threshold[node]),
        "left": tree_to_dict(tree, names, t.children_left[node]),    # feature <= threshold
        "right": tree_to_dict(tree, names, t.children_right[node]),  # feature >  threshold
    }


def window_settings():
    return {"sample_rate_hz": gm.SAMPLE_RATE_HZ, "window_samples": gm.WINDOW_SAMPLES,
            "step_samples": gm.STEP_SAMPLES, "units": "accel in g, gyro in deg/s"}


# ---- 5. Figures ---------------------------------------------------------
def save_confusion_matrix(y, predictions, title, filename):
    cm = confusion_matrix(y, predictions, labels=gm.ACTIVITIES)
    fig, ax = plt.subplots(figsize=(5.5, 4.8))
    ConfusionMatrixDisplay(cm, display_labels=gm.ACTIVITIES).plot(ax=ax, cmap="Blues", colorbar=False)
    ax.set_title(f"{title}\naccuracy {accuracy_score(y, predictions):.0%} (leave-one-recording-out)")
    ax.set_xlabel("Predicted activity")
    ax.set_ylabel("True activity")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(fig)
    return cm


def save_peak_histogram(peaks, y, axis, thresholds, classes):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.linspace(0, peaks.max() * 1.02, 50)
    for activity, color in zip(gm.ACTIVITIES, COLORS):
        ax.hist(peaks[y == activity], bins=bins, alpha=0.55, color=color, label=activity)
    for t in thresholds:
        ax.axvline(t, color="black", linestyle="--", linewidth=1.2)
        ax.text(t, ax.get_ylim()[1] * 0.97, f" {t:.2f} g", va="top", fontsize=9)
    ax.set_xlabel(f"Peak |{axis}| in a 2 s window (g)")
    ax.set_ylabel("Number of windows")
    ax.set_title(f"Model 1: peak |{axis}| per activity, dashed lines = learned thresholds\n"
                 f"bands from left to right: {' | '.join(classes)}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "model1_peak_histogram.png", dpi=150)
    plt.close(fig)


def save_tree_plot(tree, names):
    fig, ax = plt.subplots(figsize=(22, 10))
    plot_tree(tree, feature_names=names, class_names=list(tree.classes_), filled=True,
              impurity=False, proportion=True, rounded=True, fontsize=8, ax=ax)
    ax.set_title("Model 2: decision tree on all 6 IMU channels (max depth 4)")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "model2_decision_tree.png", dpi=150)
    plt.close(fig)


# ---- Summary helpers ----------------------------------------------------
def worst_mixups(cm, n=3):
    """The biggest off-diagonal cells: (true activity, predicted as, % of that activity)."""
    mixups = []
    for i, true in enumerate(gm.ACTIVITIES):
        for j, pred in enumerate(gm.ACTIVITIES):
            if i != j and cm[i, j] / cm[i].sum() >= 0.01:  # ignore mix-ups under 1%
                mixups.append((true, pred, cm[i, j] / cm[i].sum()))
    return sorted(mixups, key=lambda m: -m[2])[:n]


def describe_mixups(cm):
    mixups = worst_mixups(cm)
    if not mixups:
        return "nothing"
    return ", ".join(f"{t} called {p} ({share:.0%} of {t})" for t, p, share in mixups)


# ---- Main ---------------------------------------------------------------
def main():
    FIGURES_DIR.mkdir(exist_ok=True)
    MODELS_DIR.mkdir(exist_ok=True)
    windows, y, recording_ids = load_dataset()

    # ---- Model 1: try each accelerometer axis, keep the best ----
    print("\nModel 1: peak |acceleration| on one axis")
    best = None
    for axis in ["ax", "ay", "az"]:
        peaks = np.array([gm.peak_abs(w, axis) for w in windows])
        predictions = leave_one_recording_out(new_model1, peaks.reshape(-1, 1), y, recording_ids)
        accuracy = accuracy_score(y, predictions)
        print(f"  {axis}: {accuracy:.1%}")
        if best is None or accuracy > best["accuracy"]:
            best = {"axis": axis, "peaks": peaks, "predictions": predictions, "accuracy": accuracy}
    axis, peaks = best["axis"], best["peaks"]
    print(f"  best axis: {axis}")

    # Final Model 1: train on ALL windows (testing is already done above)
    model1 = new_model1().fit(peaks.reshape(-1, 1), y)
    thresholds, classes = tree_to_bands(model1)
    model1_json = {"model": "threshold", "feature": f"peak |{axis}| over the window",
                   "axis": axis, "thresholds": thresholds, "classes": classes,
                   "rule": "peak <= thresholds[i] -> classes[i]; above every threshold -> classes[-1]",
                   **window_settings()}
    (MODELS_DIR / "model1_thresholds.json").write_text(json.dumps(model1_json, indent=2))
    print("  thresholds (g):", ", ".join(f"{t:.3f}" for t in thresholds), "->", " | ".join(classes))

    # ---- Model 2: 30 features, depth-4 tree ----
    print("\nModel 2: decision tree on all 6 channels")
    names = gm.feature_names()
    X = np.array([gm.all_features(w) for w in windows])
    predictions2 = leave_one_recording_out(new_model2, X, y, recording_ids)
    accuracy2 = accuracy_score(y, predictions2)
    print(f"  accuracy: {accuracy2:.1%}")

    model2 = new_model2().fit(X, y)
    model2_json = {"model": "tree", "features": names,
                   "rule": "at each node: feature <= threshold -> left, else right",
                   **window_settings(), "tree": tree_to_dict(model2, names)}
    (MODELS_DIR / "model2_tree.json").write_text(json.dumps(model2_json, indent=2))
    used = [names[i] for i in np.argsort(-model2.feature_importances_) if model2.feature_importances_[i] > 0]
    print("  features the final tree uses (most important first):", ", ".join(used))

    # Check: the JSON files must give exactly the same answers as scikit-learn
    json1 = [gm.predict_threshold_model(model1_json, w) for w in windows]
    json2 = [gm.predict_tree_model(model2_json, w) for w in windows]
    assert list(model1.predict(peaks.reshape(-1, 1))) == json1, "Model 1 JSON disagrees with sklearn"
    assert list(model2.predict(X)) == json2, "Model 2 JSON disagrees with sklearn"
    print("\nSaved models/model1_thresholds.json and models/model2_tree.json "
          "(checked: same predictions as scikit-learn)")

    # ---- Figures ----
    cm1 = save_confusion_matrix(y, best["predictions"], f"Model 1: peak |{axis}| thresholds",
                                "model1_confusion_matrix.png")
    cm2 = save_confusion_matrix(y, predictions2, "Model 2: decision tree, all channels",
                                "model2_confusion_matrix.png")
    save_peak_histogram(peaks, y, axis, thresholds, classes)
    save_tree_plot(model2, names)
    print("Saved 4 figures to figures/")

    for title, cm in [("Model 1", cm1), ("Model 2", cm2)]:
        print(f"\n{title} confusion matrix (rows = true, columns = predicted):")
        print("           " + "".join(f"{a[:5]:>7s}" for a in gm.ACTIVITIES))
        for activity, row in zip(gm.ACTIVITIES, cm):
            print(f"  {activity:9s}" + "".join(f"{n:7d}" for n in row))

    # ---- Plain-English summary ----
    better, worse = ("Model 2", "Model 1") if accuracy2 >= best["accuracy"] else ("Model 1", "Model 2")
    print("\n==== Summary ====")
    print(f"{better} is better: Model 1 got {best['accuracy']:.0%} and Model 2 got {accuracy2:.0%} "
          f"on recordings they never saw.")
    print(f"Model 1 mixes up: {describe_mixups(cm1)}.")
    print(f"Model 2 mixes up: {describe_mixups(cm2)}.")
    print(f"\nWhy: Model 1 only knows how hard the hardest jolt on {axis} was. Peaks per activity "
          f"(middle 80% of windows):")
    for activity in gm.ACTIVITIES:
        lo, hi = np.percentile(peaks[y == activity], [10, 90])
        print(f"  {activity:9s} {lo:.2f} - {hi:.2f} g")
    print("Where those ranges overlap, no threshold can separate the activities"
          + ("" if len(classes) == len(gm.ACTIVITIES) else
             f", so {', '.join(a for a in gm.ACTIVITIES if a not in classes)} never even gets a band")
          + ".")
    print(f"Model 2 sees much more, but its top features ({', '.join(used[:3])}) include the "
          "accelerometer mean/min/max, which mostly measure TILT: which way gravity points, i.e. "
          "how the board was strapped on that day. With only a few recordings per activity, a "
          "held-out recording strapped on at a new angle looks like whichever activity was "
          "recorded at that angle. More recordings (strapped on slightly differently each time) "
          "or features that ignore tilt (std, dominant frequency, gyro) would fix this.")


if __name__ == "__main__":
    main()
