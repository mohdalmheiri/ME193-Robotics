"""The live step counter: the trained committee from step_model.npz, run on the
ankle samples as they arrive. Plain numpy, no PyTorch.

It does exactly what training/train_steps.py does to one clip:

1. Keep the last 2 s (200 samples) of the ankle's 6 channels.
2. Every 0.5 s (50 new samples), compute the clip's 22 features
   (clip_features below, the same formulas as training's "combined" set).
3. Run the 5 nets: rescale with each net's own mean/std, two hidden layers
   of 16 with ReLU, then 2 outputs (steps per second, meters per second),
   below 0 -> 0. The committee's answer is the average of the 5.
4. Add rate x 0.5 s to the step count and speed x 0.5 s to the distance,
   and add the clip's +/- (the leave-one-out error of the pace its step rate
   falls in, as in train_steps.clip_uncertainty).

training/check_live_math.py feeds saved recordings through this file and
checks it gives the same features and outputs as train_steps.py.
"""
import numpy as np

CHANNELS = 6                       # ax ay az (g), gx gy gz (deg/s)


def clip_features(x):
    """The 22 features of one clip (rows = samples, 6 columns), in the order
    of the model's feature_names. The same formulas as clip_features in
    training/train_steps.py with FEATURE_SET = "combined":

    - spread (standard deviation) and peak (largest absolute value) of each
      of the 6 channels: 12 numbers that depend on how the sensor sits;
    - for acceleration and rotation each, the spread and peak of the overall
      size (whatever the direction) and the spread along the clip's own three
      main directions, largest first: 10 numbers that don't."""
    per_axis = np.concatenate([x.std(axis=0), np.abs(x).max(axis=0)])
    free = []
    for v in (x[:, :3], x[:, 3:]):
        size = np.linalg.norm(v, axis=1)
        main_spreads = np.sqrt(np.clip(np.linalg.eigvalsh(np.cov(v.T))[::-1], 0, None))
        free += [size.std(), size.max(), *main_spreads]
    return np.concatenate([per_axis, free])


class Committee:
    """The 5 trained nets, loaded from step_model.npz."""

    def __init__(self, path):
        m = np.load(path)
        self.W = [m["W1"], m["W2"], m["W3"]]          # each: (nets, outputs, inputs)
        self.b = [m["b1"], m["b2"], m["b3"]]
        self.mean, self.std = m["mean"], m["std"]     # each net's own rescaling
        self.clip = int(m["clip_samples"])            # 200 samples = 2 s
        self.hop = int(m["hop_samples"])              # 50 samples = 0.5 s
        self.rate_hz = int(m["rate_hz"])
        self.n_features = len(m["feature_names"])
        # The +/- per pace group (see train_steps.uncertainty_table)
        self.unc_edges = m["unc_rate_edges"]
        self.unc_steps_frac, self.unc_dist_frac = m["unc_steps_frac"], m["unc_dist_frac"]
        self.unc_steps_per_s, self.unc_dist_per_s = m["unc_steps_per_s"], m["unc_dist_per_s"]

    def run(self, features):
        """One clip's features -> (steps/s, m/s) averaged over the 5 nets, and
        net 1's two hidden layers (16 values each, after ReLU) for the dashboard."""
        outputs, hidden = [], None
        for k in range(len(self.W[0])):
            h1 = np.maximum((features - self.mean[k]) / self.std[k] @ self.W[0][k].T + self.b[0][k], 0)
            h2 = np.maximum(h1 @ self.W[1][k].T + self.b[1][k], 0)
            outputs.append(np.maximum(h2 @ self.W[2][k].T + self.b[2][k], 0))
            if k == 0:
                hidden = (h1, h2)
        rate, speed = np.mean(outputs, axis=0)
        return float(rate), float(speed), hidden

    def uncertainty(self, rate, speed, seconds):
        """The +/- one clip adds (steps, meters): the leave-one-out error of
        the pace group its step rate falls in. Same as train_steps.clip_uncertainty."""
        g = int(np.searchsorted(self.unc_edges, rate))
        steps = self.unc_steps_frac[g] * rate * seconds + self.unc_steps_per_s[g] * seconds
        meters = self.unc_dist_frac[g] * speed * seconds + self.unc_dist_per_s[g] * seconds
        return float(steps), float(meters)


class LiveCounter:
    """Running totals from the samples as they arrive. Call add() with each
    sample; every hop samples it runs the committee on the last clip."""

    def __init__(self, committee):
        self.c = committee
        self.window = np.zeros((committee.clip, CHANNELS))   # the last 2 s, oldest first
        self.ok = np.zeros(committee.clip, bool)             # which of them are real readings
        self.filled = 0                                      # samples in the window so far
        self.since_clip = 0                                  # new samples since the last clip
        self.reset()

    def reset(self):
        """Back to 0 steps and 0 m (the Reset button). The window is kept, so
        counting carries on without waiting 2 s."""
        self.steps = self.distance = self.steps_unc = self.distance_unc = 0.0
        self.rate = self.speed = 0.0
        self.hidden = (np.zeros(16), np.zeros(16))
        self.clips = 0
        self.seconds = 0.0           # time counted since the reset (0.5 s per clip)

    def add(self, sample, ok=True):
        """One sample (6 values). ok=False marks a sample that isn't a real
        reading (all 0 or all -1). Returns True when this sample finished a clip."""
        self.window = np.roll(self.window, -1, axis=0)
        self.window[-1] = sample
        self.ok = np.roll(self.ok, -1)
        self.ok[-1] = ok
        self.filled = min(self.filled + 1, self.c.clip)
        self.since_clip += 1
        if self.filled < self.c.clip or self.since_clip < self.c.hop:
            return False
        self.since_clip = 0
        self.count_clip()
        return True

    def count_clip(self):
        seconds = self.c.hop / self.c.rate_hz                  # each clip stands for 0.5 s
        self.clips += 1
        self.seconds += seconds
        if not self.ok.all():
            # Part of the window isn't real readings (the sensor's red banner):
            # count nothing rather than let the net guess from garbage
            self.rate = self.speed = 0.0
            return
        self.rate, self.speed, self.hidden = self.c.run(clip_features(self.window))
        self.steps += self.rate * seconds
        self.distance += self.speed * seconds
        more_steps, more_m = self.c.uncertainty(self.rate, self.speed, seconds)
        self.steps_unc += more_steps
        self.distance_unc += more_m

    def totals(self):
        return {"steps": self.steps, "steps_unc": self.steps_unc,
                "distance_m": self.distance, "distance_unc": self.distance_unc}
