"""Shared gait code: loading recordings, cutting windows, computing features,
and running a saved model from its JSON file.

Only needs numpy (no scikit-learn), so the same file can run on the UNO Q
later. train.py uses it for training, and the board will use it for
predicting, so both sides compute features in exactly the same way.

Units in the CSVs: acceleration in g, rotation (gyro) in degrees per second.
"""
import csv
import json

import numpy as np

# ---- Settings ------------------------------------------------------------
SAMPLE_RATE_HZ = 100     # the sketch samples the MPU-6050 100 times a second
TRIM_SECONDS = 2         # cut this much from the start and end of each recording
                         # (pressing Start/Stop on the phone isn't real walking etc.)
WINDOW_SAMPLES = 200     # one window = 2 seconds of data
STEP_SAMPLES = 50        # slide the window forward 0.5 s at a time (windows overlap)

CHANNELS = ["ax", "ay", "az", "gx", "gy", "gz"]   # the 6 IMU outputs, in CSV order
STATS = ["mean", "std", "min", "max", "dom_freq"]  # Model 2 v1's 5 numbers per channel
MAGNITUDE_STATS = ["mean", "std", "max", "dom_freq"]  # Model 2 v2's 4 numbers per magnitude
ACTIVITIES = ["Standing", "Walking", "Running", "Biking"]  # fixed order for tables/plots


# ---- Loading and windowing ----------------------------------------------
def load_recording(path):
    """Read one CSV. Returns (data, activity): data has one row per sample and
    one column per channel (ax, ay, az, gx, gy, gz)."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    data = np.array([[float(row[c]) for c in CHANNELS] for row in rows])
    activity = rows[0]["activity"]
    return data, activity


def make_windows(data):
    """Trim the ends, then cut the recording into overlapping 2 s windows.
    Returns an array shaped (number of windows, 200 samples, 6 channels)."""
    trim = TRIM_SECONDS * SAMPLE_RATE_HZ
    data = data[trim:len(data) - trim]
    starts = range(0, len(data) - WINDOW_SAMPLES + 1, STEP_SAMPLES)
    return np.array([data[s:s + WINDOW_SAMPLES] for s in starts])


# ---- Features -----------------------------------------------------------
def peak_abs(window, channel):
    """Model 1's only feature: the biggest absolute value on one channel."""
    return float(np.max(np.abs(window[:, CHANNELS.index(channel)])))


def dominant_frequency(signal):
    """The frequency (Hz) the signal repeats at most strongly, e.g. your step rate.
    Subtract the mean first, otherwise the steady part (gravity) always "wins"."""
    spectrum = np.abs(np.fft.rfft(signal - np.mean(signal)))
    freqs = np.fft.rfftfreq(len(signal), d=1 / SAMPLE_RATE_HZ)
    spectrum[0] = 0  # skip 0 Hz (the leftover average)
    return float(freqs[np.argmax(spectrum)])


def feature_names():
    """Names of Model 2 v1's 30 features, e.g. "ax_mean", "gz_dom_freq"."""
    return [f"{c}_{s}" for c in CHANNELS for s in STATS]


def all_features(window):
    """Model 2 v1's features: mean, std, min, max and dominant frequency for each
    of the 6 channels (30 numbers), in the same order as feature_names()."""
    values = []
    for i in range(len(CHANNELS)):
        signal = window[:, i]
        values += [float(np.mean(signal)), float(np.std(signal)),
                   float(np.min(signal)), float(np.max(signal)),
                   dominant_frequency(signal)]
    return values


def feature_names_v2():
    """Names of Model 2 v2's 9 features, e.g. "acc_mag_std", "gyro_top_axis_dom_freq"."""
    return ([f"acc_mag_{s}" for s in MAGNITUDE_STATS]
            + [f"gyro_mag_{s}" for s in MAGNITUDE_STATS]
            + ["gyro_top_axis_dom_freq"])


def magnitude_features(window):
    """Model 2 v2's features, which don't care how the board is tilted.

    Magnitude = the length of the (x, y, z) arrow: sqrt(x^2 + y^2 + z^2).
    Turning the board changes how that arrow splits across x, y and z, but
    not its length. Standing still, the acceleration magnitude is about 1 g
    (just gravity) whichever way the board faces.

    For both magnitudes: mean, std, max and dominant frequency (8 numbers).
    Plus one more: the rhythm of whichever gyro axis swings the most in this
    window (a magnitude can repeat at double the real rhythm, because swinging
    forward and swinging back both make it big)."""
    acc_mag = np.linalg.norm(window[:, 0:3], axis=1)   # ax, ay, az -> one number per sample
    gyro_mag = np.linalg.norm(window[:, 3:6], axis=1)  # gx, gy, gz -> one number per sample
    values = []
    for signal in (acc_mag, gyro_mag):
        values += [float(np.mean(signal)), float(np.std(signal)),
                   float(np.max(signal)), dominant_frequency(signal)]
    busiest = np.argmax(np.std(window[:, 3:6], axis=0))  # 0 = gx, 1 = gy, 2 = gz
    values.append(dominant_frequency(window[:, 3 + busiest]))
    return values


# Which feature function goes with which saved tree ("feature_set" in its JSON)
FEATURE_SETS = {"v1": all_features, "v2": magnitude_features}


# ---- Running a saved model ---------------------------------------------
def load_model(path):
    with open(path) as f:
        return json.load(f)


def predict_threshold_model(model, window):
    """Model 1: find which band the peak falls in.
    thresholds = [t1, t2, t3] and classes = [c0, c1, c2, c3] mean:
    peak <= t1 -> c0,  t1 < peak <= t2 -> c1,  ...,  peak > t3 -> c3."""
    peak = peak_abs(window, model["axis"])
    for threshold, activity in zip(model["thresholds"], model["classes"]):
        if peak <= threshold:
            return activity
    return model["classes"][-1]


def predict_tree_model(model, window):
    """Model 2 (v1 or v2): start at the top of the tree and follow the questions
    down ("is feature <= threshold?" yes -> left, no -> right) until a leaf."""
    compute = FEATURE_SETS[model.get("feature_set", "v1")]
    features = dict(zip(model["features"], compute(window)))
    node = model["tree"]
    while "activity" not in node:
        node = node["left"] if features[node["feature"]] <= node["threshold"] else node["right"]
    return node["activity"]
