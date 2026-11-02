# Window features for the swing classifier. Shared by train_swing_classifier.py
# and game.py so the model always sees features computed the same way.
import numpy as np

WINDOW_S = 0.4      # seconds of IMU readings per window (~20 readings at 50/s)
MIN_SAMPLES = 8     # skip windows with fewer readings than this (gaps in the data)

FEATURES = [
    "gyro_max", "gyro_mean", "gyro_std",          # gyro magnitude: how fast it rotates
    "acc_max", "acc_min", "acc_mean", "acc_std",  # acc magnitude (milli-g, ~1000 when still)
    "acc_diff_max",                               # biggest difference from gravity (1000)
    "ax_absmax", "ay_absmax", "az_absmax",        # biggest value on each axis
    "gx_absmax", "gy_absmax", "gz_absmax",
]


def window_features(readings):
    """readings: N x 6 array of (ax, ay, az, gx, gy, gz). Returns one row of FEATURES."""
    r = np.asarray(readings, dtype=float)
    acc = np.linalg.norm(r[:, :3], axis=1)
    gyro = np.linalg.norm(r[:, 3:], axis=1)
    return [gyro.max(), gyro.mean(), gyro.std(),
            acc.max(), acc.min(), acc.mean(), acc.std(),
            np.abs(acc - 1000).max(),
            *np.abs(r).max(axis=0)]
