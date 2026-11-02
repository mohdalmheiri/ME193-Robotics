# Step 6b: train a logistic-regression swing classifier from swing_data.csv.
# Run:  python train_swing_classifier.py
# Saves swing_model.joblib, which game.py loads.
import csv
import os
from collections import defaultdict

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from swing_features import FEATURES, MIN_SAMPLES, WINDOW_S, window_features

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "swing_data.csv")
MODEL_FILE = os.path.join(HERE, "swing_model.joblib")

SWING_SHIFTS = [0.0, 0.05, 0.1, 0.15, 0.2]   # positive windows END this long after the peak, so the
                                              # model learns to spot the peak anywhere in the window
                                              # (the game's window always ends "now")
IDLE_STEP = 0.1          # slide not-a-swing windows by this much
MIN_PEAK_SCORE = 0.3     # a "swing" event this weak (see motion_score) probably had no swing - skipped
TEST_FRACTION = 0.25     # share of EVENTS (not windows) held out for testing
SEED = 0


def motion_score(rows):
    """How strong the motion is at each reading (1.0 = the old GYRO 560 / ACC diff 500 thresholds)."""
    acc = np.linalg.norm(rows[:, :3], axis=1)
    gyro = np.linalg.norm(rows[:, 3:], axis=1)
    return np.maximum(gyro / 560, np.abs(acc - 1000) / 500)


def window_ending(t, rows, end):
    """Readings in (end - WINDOW_S, end], or None if there are too few."""
    m = (t > end - WINDOW_S) & (t <= end)
    return rows[m] if m.sum() >= MIN_SAMPLES else None


def load_windows():
    sessions = defaultdict(list)
    with open(DATA_FILE) as f:
        for r in csv.DictReader(f):
            sessions[r["session"]].append(r)

    X, y, groups = [], [], []
    skipped = 0
    for session, data in sessions.items():
        data.sort(key=lambda r: float(r["t"]))
        t = np.array([float(r["t"]) for r in data])
        rows = np.array([[float(r[k]) for k in ("ax", "ay", "az", "gx", "gy", "gz")] for r in data])
        labels = np.array([r["label"] for r in data])
        events = np.array([r["event"] for r in data])

        # swings: windows around the motion peak after each beep
        for ev in sorted(set(events[labels == "swing"])):
            idx = np.where(events == ev)[0]
            score = motion_score(rows[idx])
            if score.max() < MIN_PEAK_SCORE:
                skipped += 1
                continue
            peak_t = t[idx[score.argmax()]]
            for shift in SWING_SHIFTS:
                win = window_ending(t, rows, peak_t + shift)
                if win is not None:
                    X.append(window_features(win)); y.append(1); groups.append(ev)

        # not-a-swing: sliding windows that lie entirely inside the not_swing round
        idle = labels == "not_swing"
        if idle.any():
            t_idle = t[idle]
            end = t_idle.min() + WINDOW_S
            while end <= t_idle.max():
                m = (t > end - WINDOW_S) & (t <= end)
                if m.sum() >= MIN_SAMPLES and idle[m].all():
                    i = np.where(m)[0][-1]
                    X.append(window_features(rows[m])); y.append(0); groups.append(events[i])
                end += IDLE_STEP

    if skipped:
        print(f"Skipped {skipped} swing event(s) with almost no motion (missed beep?)")
    return np.array(X), np.array(y), np.array(groups)


def split_by_event(y, groups):
    """Hold out whole events, chosen separately from swings and not-swings so both are in the test set."""
    rng = np.random.default_rng(SEED)
    test_events = set()
    for label in (0, 1):
        evs = sorted(set(groups[y == label]))
        rng.shuffle(evs)
        test_events |= set(evs[:max(1, round(len(evs) * TEST_FRACTION))])
    test = np.array([g in test_events for g in groups])
    return ~test, test


def make_model():
    return make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000))


def main():
    if not os.path.exists(DATA_FILE):
        print(f"No data yet - run collect_swing_data.py first ({DATA_FILE} not found).")
        return
    X, y, groups = load_windows()
    n_sw, n_idle = len(set(groups[y == 1])), len(set(groups[y == 0]))
    print(f"{len(y)} windows: {int(y.sum())} swing (from {n_sw} swings), "
          f"{int((y == 0).sum())} not-a-swing (from {n_idle} 2-second chunks)")
    if n_sw < 4 or n_idle < 4:
        print("Not enough events to train and test - record more data.")
        return

    train, test = split_by_event(y, groups)
    model = make_model().fit(X[train], y[train])
    pred = model.predict(X[test])
    print(f"\nTest set: {len(set(groups[test]))} events never seen in training, {test.sum()} windows")
    print(f"Test accuracy: {(pred == y[test]).mean():.1%}")
    cm = confusion_matrix(y[test], pred, labels=[0, 1])
    print("\nConfusion matrix (rows = truth, columns = prediction):")
    print(f"{'':>14}{'not swing':>11}{'swing':>8}")
    print(f"{'not swing':>14}{cm[0, 0]:>11}{cm[0, 1]:>8}")
    print(f"{'swing':>14}{cm[1, 0]:>11}{cm[1, 1]:>8}")

    # features are standardized, so coefficient size = how much the model relies on each one
    coef = model[-1].coef_[0]
    print("\nMost important features (+ pushes toward swing, - toward not-a-swing):")
    for i in np.argsort(-np.abs(coef))[:3]:
        print(f"  {FEATURES[i]:<14} {coef[i]:+.2f}")

    # final model: same settings, trained on ALL the data
    final = make_model().fit(X, y)
    joblib.dump({"model": final, "features": FEATURES, "window_s": WINDOW_S}, MODEL_FILE)
    print(f"\nSaved {MODEL_FILE} (trained on all {len(y)} windows)")


if __name__ == "__main__":
    main()
