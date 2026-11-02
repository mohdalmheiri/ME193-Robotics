"""Train and fairly test the HW7 step counter: steps per second and meters per second
from 2-second clips of the ankle IMU (and, for comparison, the pocket phone).

    python train_steps.py          (from this folder, or anywhere; takes a few minutes)

What it does:

1. Loads every good trial: each row of data/trials.csv that isn't listed in
   data/excluded_trials.csv. The ankle and phone recordings are lined up on
   the stomp, found the same way data/check_recordings.py finds it.
2. Keeps only the moving stretch: from the ankle's first swing after the
   stomp to its last swing at the finish (standing at the finish line would
   otherwise be labelled with the walking rate). Zero-step trials (Stand,
   Fidget, LegSwing) use everything after the stomp.
3. Cuts it into 2 s clips, a new one every 0.5 s. Each clip is labelled with
   its trial's step rate (steps / moving time) and speed (distance / moving
   time); zero-step trials get 0 for both.
4. Features per clip: 10 that don't depend on how the sensor sits on the
   leg (FEATURE_SET = "direction_free", see clip_features): the overall size
   of the acceleration and rotation, and their spread along the clip's own
   main directions. No averages: those mostly measure how the sensor is
   tilted, not how you move. (The earlier "combined" set added the spread and
   peak of each sensor axis, 22 in all; test walks with the sensor strapped
   at a new angle came out 14% low with it.)
5. A small net, features -> 16 -> 16 -> 2 (steps/s, m/s), trained with mean
   squared error until the loss flattens.
6. Leave-one-trial-out testing: for every trial, a committee of 5 nets
   (different random starts) is trained without it and estimates its total
   steps and distance. The +/- is the spread between the 5 nets. Done twice:
   ankle only, and ankle + phone. A plain peak counter is the non-neural
   comparison.
7. Saves the plots and tables, and step_model.npz: the ankle-only committee
   trained on every good trial, runnable on the UNO Q with plain numpy
   (see numpy_predict below). It also holds the +/- the dashboard shows,
   taken from the leave-one-out errors per pace, not from the committee's
   spread: the 5 nets agree with each other much more closely than they
   agree with the truth (see uncertainty_table and clip_uncertainty).

Outputs: ../media/train_loss.png, ../media/steps_est_vs_true.png,
results.md (errors per pace) and results_per_trial.csv in this folder, and
step_model.npz both here and in ../uno_q/python/ (the copy the board loads).
"""
import csv
import shutil
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save figures to files, don't open windows
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "data"))
import check_recordings as cr  # noqa: E402  (the same loading and stomp finding as the checks)

# ---- Settings --------------------------------------------------------------------
RATE = cr.RATE                   # ankle samples per second (100)
CLIP = 2 * RATE                  # 2 s clips...
HOP = RATE // 2                  # ...a new one every 0.5 s
MOVING_DPS = cr.MOVING_DPS       # the leg is swinging when the ankle rotates faster than this (60 deg/s)
NO_STEP = ["Stand", "Fidget", "LegSwing"]
SOFT_STOMP_S = 3                 # a stomp too soft for the checks' 3 g minimum (stomping while seated)
                                 # is taken as the biggest spike in the first 3 s instead
PACES = ["Walk_slow", "Walk_normal", "Walk_fast", "Run"]
CHANNELS = ["ax", "ay", "az", "gx", "gy", "gz"]
# Which features describe a clip (see clip_features):
#   "direction_free": 10 per sensor that don't depend on how it sits on the leg
#   "combined": those plus the spread and peak of each sensor axis (22; saved as step_model_22features.npz)
#   "per_axis": only the spread and peak of each sensor axis (12)
FEATURE_SET = "direction_free"

N_NETS = 5                       # committee size
HIDDEN = 16
LEARNING_RATE = 0.01
MAX_EPOCHS = 4000                # a full pass over the training clips per epoch
PLATEAU_EPOCHS = 100             # "flattened" = less than PLATEAU_GAIN better than
PLATEAU_GAIN = 0.01              # PLATEAU_EPOCHS ago (1%)

# Peak counter (the non-neural comparison). Fixed in advance, not tuned on the data.
PEAK_SMOOTH = RATE // 10         # smooth the rotation over 0.1 s first
PEAK_DPS = 100                   # a leg swing reaches at least 100 deg/s...
PEAK_GAP = int(0.4 * RATE)       # ...and swings of the same leg are at least 0.4 s apart

# Plot colors: the first three slots of the reference categorical palette, in order
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
MEDIA = PROJECT / "media"
BOARD_MODEL = PROJECT / "uno_q" / "python" / "step_model.npz"   # the copy the UNO Q app loads


# ---- 1-3. Loading, lining up, moving stretch -----------------------------------------
def good_trials():
    """The rows of trials.csv (with trial_corrections.csv applied) not in
    excluded_trials.csv, for the paces and the zero-step activities. Test and
    Outdoor trials are kept for testing the finished counter, never trained on."""
    trials = cr.load_trials()
    excluded = cr.load_excluded()
    return [t for t in trials if t["file"] not in excluded and t["activity"] in PACES + NO_STEP]


def phone_on_ankle_time(phone, offset, n):
    """The phone's 6 channels resampled onto the ankle's sample times, so a clip
    takes the same rows from both. phone time = ankle time + offset."""
    t = np.arange(n) / RATE + offset
    acc, gyro = phone["acc"], phone["gyro"]
    columns = [np.interp(t, acc[:, 0], acc[:, i]) / cr.G for i in (1, 2, 3)]          # m/s^2 -> g
    columns += [np.interp(t, gyro[:, 0], gyro[:, i]) * 180 / np.pi for i in (1, 2, 3)]  # rad/s -> deg/s
    return np.column_stack(columns)


def load_trial(trial):
    """One trial, lined up and labelled. Returns a dict with the ankle and
    phone samples (same rows), the moving stretch [lo, hi) and the labels."""
    name = trial["file"][:-4]
    ankle, start = cr.load_ankle(trial["file"])
    t = np.arange(len(ankle)) / RATE
    mag = np.linalg.norm(ankle[:, :3], axis=1)
    stomp = cr.find_ankle_stomp(t, mag)
    if stomp is None:
        # Too soft for the checks (LegSwing T04, stomped while seated): the
        # biggest spike in the first seconds is still the stomp
        stomp = cr.find_stomp(t, mag, 0, SOFT_STOMP_S)

    # The phone's stomp, looked for near where the clocks put it (as in the checks)
    phone = cr.load_phone(cr.PHONE / name)
    expected = start + stomp["t"] - phone["start"]
    phone_mag = np.linalg.norm(phone["acc"][:, 1:], axis=1) / cr.G
    phone_stomp = cr.find_stomp(phone["acc"][:, 0], phone_mag,
                                expected - cr.PHONE_SEARCH_S, expected + cr.PHONE_SEARCH_S)
    offset = phone_stomp["t"] - stomp["t"]

    # The moving stretch
    if trial["activity"] in NO_STEP:
        lo, hi = stomp["i"] + RATE, len(ankle)              # 1 s after the stomp to the end
    else:
        after = stomp["i"] + RATE // 2                       # past the stomp's own wobble
        swinging = np.flatnonzero(np.linalg.norm(ankle[after:, 3:], axis=1) > MOVING_DPS) + after
        lo, hi = swinging[0], swinging[-1] + 1
    moving_s = (hi - lo) / RATE
    steps, distance = int(trial["steps"]), float(trial["distance_m"])
    return {
        "name": name, "activity": trial["activity"], "steps": steps, "distance": distance,
        "ankle": ankle, "phone": phone_on_ankle_time(phone, offset, len(ankle)),
        "stomp_i": stomp["i"], "lo": lo, "hi": hi, "moving_s": moving_s,
        # step rate and speed over the moving stretch (0 for the zero-step trials)
        "rate": 0.0 if trial["activity"] in NO_STEP else steps / moving_s,
        "speed": 0.0 if trial["activity"] in NO_STEP else distance / moving_s,
    }


# ---- 3-4. Clips and features --------------------------------------------------------------
def clip_starts(tr):
    """Where each 2 s clip starts (sample index), every 0.5 s along the moving stretch."""
    return list(range(tr["lo"], tr["hi"] - CLIP + 1, HOP))


def per_axis_features(x):
    """The spread and peak of each of the 6 channels of one clip (rows =
    samples, columns ax ay az gx gy gz): 12 numbers. These depend on how the
    sensor sits on the leg: re-strapped at another angle, the same swing
    shows up on different axes."""
    return np.concatenate([x.std(axis=0), np.abs(x).max(axis=0)])


def direction_free_features(x):
    """For acceleration and rotation each: the spread and peak of the overall
    size (magnitude, whatever the direction), and the spread along the clip's
    own three main directions, largest first (the square roots of the
    covariance's eigenvalues): 10 numbers. The same movement gives the same
    numbers however the sensor is turned."""
    free = []
    for v in (x[:, :3], x[:, 3:]):
        size = np.linalg.norm(v, axis=1)
        main_spreads = np.sqrt(np.clip(np.linalg.eigvalsh(np.cov(v.T))[::-1], 0, None))
        free += [size.std(), size.max(), *main_spreads]
    return np.array(free)


def clip_features(x):
    """The features of one clip for FEATURE_SET (the board's step_counter.py
    has the same formulas)."""
    if FEATURE_SET == "per_axis":
        return per_axis_features(x)
    if FEATURE_SET == "direction_free":
        return direction_free_features(x)
    return np.concatenate([per_axis_features(x), direction_free_features(x)])


def feature_names(with_phone):
    def one(sensor):
        per_axis = [f"{sensor}_{c}_spread" for c in CHANNELS] + [f"{sensor}_{c}_peak" for c in CHANNELS]
        free = [f"{sensor}_{kind}_{part}" for kind in ("acc", "gyro")
                for part in ("size_spread", "size_peak", "main1_spread", "main2_spread", "main3_spread")]
        return {"per_axis": per_axis, "direction_free": free, "combined": per_axis + free}[FEATURE_SET]
    return one("ankle") + (one("phone") if with_phone else [])


def trial_clips(tr, with_phone):
    """Features X (one row per clip) and labels y (steps/s, m/s) for one trial."""
    rows = []
    for s in clip_starts(tr):
        f = clip_features(tr["ankle"][s:s + CLIP])
        if with_phone:
            f = np.concatenate([f, clip_features(tr["phone"][s:s + CLIP])])
        rows.append(f)
    X = np.array(rows)
    y = np.tile([tr["rate"], tr["speed"]], (len(rows), 1))
    return X, y


def clip_seconds(tr):
    """How many seconds of the moving stretch each clip stands for, so that
    rate x seconds, added up, gives the trial's total. Each clip stands for the
    0.5 s around its centre; the centres don't reach the first and last second
    of the stretch, so the first and last clip also cover those ends."""
    starts = np.array(clip_starts(tr))
    centres = (starts + CLIP / 2) / RATE
    seconds = np.full(len(starts), HOP / RATE)
    seconds[0] += centres[0] - HOP / RATE / 2 - tr["lo"] / RATE
    seconds[-1] += tr["hi"] / RATE - (centres[-1] + HOP / RATE / 2)
    return seconds


# ---- 5. The net -------------------------------------------------------------------------------
class StepNet(nn.Module):
    """features -> 16 -> 16 -> 2 (steps per second, meters per second)."""

    def __init__(self, n_inputs):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(n_inputs, HIDDEN), nn.ReLU(),
            nn.Linear(HIDDEN, HIDDEN), nn.ReLU(),
            nn.Linear(HIDDEN, 2),
        )

    def forward(self, x):
        return self.layers(x)


def train_net(X, y, seed, X_test=None, y_test=None):
    """Train one net on all the clips at once (they're few) until the loss
    flattens. The inputs are rescaled with the training clips' mean and spread
    only. The held-out loss, if given, is only recorded for the loss plot:
    it never decides anything. Returns the net, the rescaling, and the losses."""
    torch.manual_seed(seed)
    mean, std = X.mean(axis=0), X.std(axis=0) + 1e-6
    Xt = torch.tensor((X - mean) / std, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.float32)
    test = None
    if X_test is not None:
        test = (torch.tensor((X_test - mean) / std, dtype=torch.float32), torch.tensor(y_test, dtype=torch.float32))

    net = StepNet(X.shape[1])
    optimizer = torch.optim.Adam(net.parameters(), lr=LEARNING_RATE)
    loss_fn = nn.MSELoss()
    train_losses, test_losses = [], []
    for epoch in range(MAX_EPOCHS):
        optimizer.zero_grad()
        loss = loss_fn(net(Xt), yt)
        loss.backward()
        optimizer.step()
        train_losses.append(loss.item())
        if test is not None:
            with torch.no_grad():
                test_losses.append(loss_fn(net(test[0]), test[1]).item())
        # Flattened: barely better than PLATEAU_EPOCHS ago
        if epoch >= PLATEAU_EPOCHS:
            before = train_losses[-PLATEAU_EPOCHS - 1]
            if before - train_losses[-1] < PLATEAU_GAIN * before:
                break
    return net, mean, std, train_losses, test_losses


def predict(net, mean, std, X):
    """Steps/s and m/s for each clip. Neither can be negative, so below 0 -> 0."""
    with torch.no_grad():
        out = net(torch.tensor((X - mean) / std, dtype=torch.float32)).numpy()
    return np.maximum(out, 0)


# ---- 6. Fair testing ------------------------------------------------------------------------
def leave_one_trial_out(trials, with_phone):
    """For each trial: train a committee without it, then estimate its totals.
    Returns one result per trial, and the loss curves for the plot."""
    clips = [trial_clips(tr, with_phone) for tr in trials]
    results, curves = [], []
    for i, tr in enumerate(trials):
        X = np.vstack([c[0] for j, c in enumerate(clips) if j != i])
        y = np.vstack([c[1] for j, c in enumerate(clips) if j != i])
        seconds = clip_seconds(tr)
        totals = []
        for k in range(N_NETS):
            net, mean, std, train_l, test_l = train_net(X, y, seed=1000 * i + k, X_test=clips[i][0], y_test=clips[i][1])
            out = predict(net, mean, std, clips[i][0])
            totals.append((out * seconds[:, None]).sum(axis=0))   # rate x seconds, added up
            curves.append((train_l, test_l))
        totals = np.array(totals)                                  # rows: nets; columns: steps, meters
        results.append({
            "steps_est": totals[:, 0].mean(), "steps_pm": totals[:, 0].std(),
            "dist_est": totals[:, 1].mean(), "dist_pm": totals[:, 1].std(),
        })
        print(f"  {'ankle + phone' if with_phone else 'ankle only'}: {i + 1}/{len(trials)} {tr['name']}: "
              f"{results[-1]['steps_est']:.1f} +/- {results[-1]['steps_pm']:.1f} steps (true {tr['steps']})", flush=True)
    return results, curves


def peak_count(tr):
    """The non-neural step counter. Each swing of the right leg (the one with
    the sensor) makes one big rotation peak around the leg's main swing axis,
    so steps = 2 x the peaks. Runs on everything after the stomp (from the
    start for a recording without one, like a Test walk: stomp_i None); it
    doesn't need the moving stretch or any training."""
    start = 0 if tr.get("stomp_i") is None else tr["stomp_i"] + RATE // 2
    g = tr["ankle"][start:, 3:]
    # The main swing axis: the direction with the most rotation (no labels used)
    values, vectors = np.linalg.eigh(np.cov(g.T))
    swing = g @ vectors[:, -1]
    if swing.max() < -swing.min():
        swing = -swing                       # make the big mid-swing peaks positive
    swing = np.convolve(swing, np.ones(PEAK_SMOOTH) / PEAK_SMOOTH, mode="same")
    peaks = [i for i in range(1, len(swing) - 1)
             if swing[i] > PEAK_DPS and swing[i] >= swing[i - 1] and swing[i] > swing[i + 1]]
    kept = []                                # the highest peak within each 0.4 s
    for p in peaks:
        if kept and p - kept[-1] < PEAK_GAP:
            if swing[p] > swing[kept[-1]]:
                kept[-1] = p
        else:
            kept.append(p)
    return 2 * len(kept)


# ---- The +/- for the dashboard -------------------------------------------------------------
UNC_GROUPS = ["Zero-step"] + PACES


def uncertainty_table(trials, results):
    """How far off the ankle-only estimates really were in the leave-one-out
    test, per group, as the root-mean-square (a typical error, like a standard
    deviation). Walking paces: a fraction of the steps and distance. Zero-step
    trials have no true total to take a fraction of, so for them it's false
    steps (and meters) per second. Also the step rates that separate the
    groups, so the board can tell from the net's own estimate which one applies."""
    table = {"groups": UNC_GROUPS, "steps_frac": [], "dist_frac": [], "steps_per_s": [], "dist_per_s": []}
    for g in UNC_GROUPS:
        idx = [i for i, tr in enumerate(trials) if tr["activity"] == g or (g == "Zero-step" and tr["activity"] in NO_STEP)]
        rms = lambda v: float(np.sqrt(np.mean(np.square(v))))
        if g == "Zero-step":
            table["steps_frac"].append(0.0)
            table["dist_frac"].append(0.0)
            table["steps_per_s"].append(rms([results[i]["steps_est"] / trials[i]["moving_s"] for i in idx]))
            table["dist_per_s"].append(rms([results[i]["dist_est"] / trials[i]["moving_s"] for i in idx]))
        else:
            table["steps_frac"].append(rms([(results[i]["steps_est"] - trials[i]["steps"]) / trials[i]["steps"] for i in idx]))
            table["dist_frac"].append(rms([(results[i]["dist_est"] - trials[i]["distance"]) / trials[i]["distance"] for i in idx]))
            table["steps_per_s"].append(0.0)
            table["dist_per_s"].append(0.0)
    # Group boundaries: halfway between the paces' typical step rates; below
    # half the slowest pace's rate counts as not stepping
    typical = [np.mean([tr["rate"] for tr in trials if tr["activity"] == p]) for p in PACES]
    table["rate_edges"] = [typical[0] / 2] + [(a + b) / 2 for a, b in zip(typical, typical[1:])]
    return table


def clip_uncertainty(model, rate, speed, seconds):
    """The +/- one clip adds to the running totals (steps, meters), given the
    net's step rate and speed for it and the seconds it stands for. The board
    adds these up over the walk, straight (not as independent errors), since
    a trial's error is mostly a steady bias; over a whole trial of one pace
    this gives that pace's leave-one-out error."""
    g = int(np.searchsorted(model["unc_rate_edges"], rate))      # 0 = zero-step, 1.. = the paces in order
    steps = model["unc_steps_frac"][g] * rate * seconds + model["unc_steps_per_s"][g] * seconds
    meters = model["unc_dist_frac"][g] * speed * seconds + model["unc_dist_per_s"][g] * seconds
    return float(steps), float(meters)


def uncertainty_markdown(table):
    lines = ["| Group | Steps +/- | Distance +/- | Applies when the net's step rate is |",
             "|---|---|---|---|"]
    edges = table["rate_edges"] + [None]
    lower = [None] + table["rate_edges"]
    for g, sf, df, sps, dps, lo, hi in zip(table["groups"], table["steps_frac"], table["dist_frac"],
                                           table["steps_per_s"], table["dist_per_s"], lower, edges):
        steps = f"{100 * sf:.1f}% of the steps" if g != "Zero-step" else f"{sps:.2f} false steps per second"
        dist = f"{100 * df:.1f}% of the distance" if g != "Zero-step" else f"{dps:.2f} m per second"
        when = (f"below {hi:.2f}" if lo is None else f"{lo:.2f} and up" if hi is None else f"{lo:.2f} to {hi:.2f}")
        lines.append(f"| {g} | {steps} | {dist} | {when} steps/s |")
    return "\n".join(lines)


# ---- 7. The model for the UNO Q -----------------------------------------------------------------
def save_for_board(nets, path, unc):
    """The committee's weights, rescaling and settings as plain numpy arrays.
    Each net was trained with its own rescaling, so mean/std are per net too."""
    arrays = {"feature_names": np.array(feature_names(False)), "feature_set": FEATURE_SET, "clip_samples": CLIP,
              "hop_samples": HOP, "rate_hz": RATE, "outputs": np.array(["steps_per_s", "meters_per_s"])}
    for key, index in [("W1", 0), ("W2", 2), ("W3", 4)]:
        arrays[key] = np.stack([n.layers[index].weight.detach().numpy() for n, _, _ in nets])
        arrays["b" + key[1]] = np.stack([n.layers[index].bias.detach().numpy() for n, _, _ in nets])
    arrays["mean"] = np.stack([m for _, m, _ in nets])
    arrays["std"] = np.stack([s for _, _, s in nets])
    # The dashboard's +/- (see uncertainty_table and clip_uncertainty)
    arrays["unc_groups"] = np.array(unc["groups"])
    arrays["unc_rate_edges"] = np.array(unc["rate_edges"])
    for key in ("steps_frac", "dist_frac", "steps_per_s", "dist_per_s"):
        arrays["unc_" + key] = np.array(unc[key])
    np.savez(path, **arrays)


def numpy_predict(model, features):
    """What the UNO Q runs: plain numpy, no PyTorch. model = np.load("step_model.npz");
    features = one row per clip (clip_features of the 6 ankle channels). Returns
    the committee average and spread of (steps/s, m/s) for each clip."""
    outputs = []
    for k in range(len(model["W1"])):
        h = (features - model["mean"][k]) / model["std"][k]
        h = np.maximum(h @ model["W1"][k].T + model["b1"][k], 0)    # ReLU
        h = np.maximum(h @ model["W2"][k].T + model["b2"][k], 0)
        outputs.append(np.maximum(h @ model["W3"][k].T + model["b3"][k], 0))
    outputs = np.array(outputs)
    return outputs.mean(axis=0), outputs.std(axis=0)


# ---- Plots and tables -----------------------------------------------------------------------------
def style(ax):
    ax.set_facecolor("#fcfcfb")
    ax.grid(color=GRID, lw=0.8)
    ax.tick_params(colors=MUTED, labelcolor=INK_2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)


def plot_losses(curves_by_version, path):
    """Median training and held-out loss across all leave-one-out nets, per
    version. Each net stops at its own epoch; the curves end where half the
    nets have stopped, since past that a few nets would decide the median."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True, facecolor="#fcfcfb")
    for ax, (label, curves) in zip(axes, curves_by_version.items()):
        stops = np.array([len(c[0]) for c in curves])
        end = int(np.median(stops))
        def median(which):
            padded = np.full((len(curves), end), np.nan)
            for r, c in enumerate(curves):
                padded[r, :min(end, len(c[which]))] = c[which][:end]
            return np.nanmedian(padded, axis=0)
        ax.plot(median(0), color=BLUE, lw=2, label="training trials")
        ax.plot(median(1), color=ORANGE, lw=2, label="held-out trial (not used to stop)")
        ax.set_yscale("log")
        ax.set_title(f"{label}: nets stop at epoch {stops.min()}-{stops.max()} (median {end})",
                     loc="left", color=INK, fontsize=11)
        ax.set_xlabel("Epoch", color=INK_2)
        style(ax)
    axes[0].set_ylabel("Mean squared error (log scale)", color=INK_2)
    axes[0].legend(frameon=False, labelcolor=INK_2)
    fig.suptitle("Loss while training, leave-one-trial-out (median over all nets, up to the median stop)",
                 x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


def plot_estimates(trials, res_ankle, res_both, peaks, path):
    """Left: estimated vs true total steps for every held-out trial. Right: the
    estimated distance per trial, grouped by pace (every walk and run is 20 m)."""
    true_steps = np.array([tr["steps"] for tr in trials])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), facecolor="#fcfcfb", gridspec_kw={"width_ratios": [1.15, 1]})
    top = 70                                           # zoomed on the trials; anything above is labelled
    ax = axes[0]
    series = [("ankle only (net)", res_ankle, BLUE, "o", -0.6), ("ankle + phone (net)", res_both, ORANGE, "s", 0.6)]
    for label, res, color, marker, dx in series:       # side by side, so the markers don't hide each other
        ax.errorbar(true_steps + dx, [r["steps_est"] for r in res], yerr=[r["steps_pm"] for r in res],
                    fmt=marker, ms=7, color=color, mec="#fcfcfb", mew=1, elinewidth=1.2, capsize=2, label=label)
    shown = np.minimum(peaks, top - 2)
    ax.plot(true_steps, shown, "^", ms=7, color=AQUA, mec="#fcfcfb", mew=1, label="peak counter (no net)")
    off_chart = sorted(p for p in peaks if p > top - 2)   # all at 0 true steps: one label for them
    if off_chart:
        ax.annotate(f"peak counter, off the chart: {', '.join(map(str, off_chart))}", (0, top - 2), xytext=(8, -4),
                    textcoords="offset points", color=INK_2, fontsize=9)
    ax.plot([0, top], [0, top], color=MUTED, lw=1, ls="--", zorder=0)
    ax.text(44, 41, "perfect", color=MUTED, fontsize=9, ha="right")
    ax.set_xlim(-3, 45)
    ax.set_ylim(-3, top)
    ax.set_xlabel("True steps", color=INK_2)
    ax.set_ylabel("Estimated steps", color=INK_2)
    ax.set_title("Total steps per held-out trial", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, labelcolor=INK_2, loc="lower right")
    style(ax)

    ax = axes[1]
    groups = PACES + ["Zero-step"]
    for gi, g in enumerate(groups):
        idx = [i for i, tr in enumerate(trials) if tr["activity"] == g or (g == "Zero-step" and tr["activity"] in NO_STEP)]
        truth = 0 if g == "Zero-step" else 20
        ax.plot([gi - 0.35, gi + 0.35], [truth, truth], color=MUTED, lw=1, ls="--", zorder=0)
        for label, res, color, marker, dx in series:
            ax.errorbar(np.full(len(idx), gi + dx / 4), [res[i]["dist_est"] for i in idx],
                        yerr=[res[i]["dist_pm"] for i in idx], fmt=marker, ms=6, color=color, mec="#fcfcfb",
                        mew=1, elinewidth=1, capsize=2, alpha=0.9)
    ax.set_xticks(range(len(groups)), [g.replace("_", "\n").replace("-", "-\n") for g in groups], color=INK_2)
    ax.set_ylabel("Estimated distance (m)", color=INK_2)
    ax.set_title("Distance per held-out trial (dashed: the truth)", loc="left", color=INK, fontsize=11)
    style(ax)
    fig.text(0.01, 0.01, "Error bars: spread between the 5 nets of each committee. The peak counter only counts steps. "
             "Zero-step trials (Stand, Fidget, LegSwing) have 0 true steps.", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


def error_table(trials, res_ankle, res_both, peaks):
    """Errors per pace, as a markdown table: mean absolute error, and as a % of the truth."""
    groups = PACES + ["Zero-step"]
    lines = ["| Pace | Trials | Steps error: ankle only | Steps error: ankle + phone | Steps error: peak counter "
             "| Distance error: ankle only | Distance error: ankle + phone | Typical +/- (ankle only) |",
             "|---|---|---|---|---|---|---|---|"]
    for g in groups + ["All"]:
        idx = [i for i, tr in enumerate(trials)
               if g == "All" or tr["activity"] == g or (g == "Zero-step" and tr["activity"] in NO_STEP)]
        steps = np.array([trials[i]["steps"] for i in idx], float)
        dist = np.array([trials[i]["distance"] for i in idx], float)

        def err(est, truth):
            e = np.abs(np.array(est) - truth)
            pct = f" ({100 * e.sum() / truth.sum():.1f}%)" if truth.sum() > 0 else ""
            return f"{e.mean():.1f}{pct}"
        lines.append(f"| {g} | {len(idx)} "
                     f"| {err([res_ankle[i]['steps_est'] for i in idx], steps)} "
                     f"| {err([res_both[i]['steps_est'] for i in idx], steps)} "
                     f"| {err([peaks[i] for i in idx], steps)} "
                     f"| {err([res_ankle[i]['dist_est'] for i in idx], dist)} m "
                     f"| {err([res_both[i]['dist_est'] for i in idx], dist)} m "
                     f"| {np.mean([res_ankle[i]['steps_pm'] for i in idx]):.1f} steps, "
                     f"{np.mean([res_ankle[i]['dist_pm'] for i in idx]):.1f} m |")
    return "\n".join(lines)


def comparison_table(trials, res_ankle, path):
    """Ankle-only leave-one-out errors per group, next to the same test for an
    earlier model (its results_per_trial file): steps and distance per trial."""
    with open(path, newline="") as f:
        old = {r["trial"]: r for r in csv.DictReader(f)}
    lines = ["| Pace | Trials | Steps error: 22 features | Steps error: direction-free (now) "
             "| Distance error: 22 features | Distance error: direction-free (now) |", "|---|---|---|---|---|---|"]
    for g in PACES + ["Zero-step", "All"]:
        idx = [i for i, tr in enumerate(trials)
               if (g == "All" or tr["activity"] == g or (g == "Zero-step" and tr["activity"] in NO_STEP)) and tr["name"] in old]
        steps = np.array([trials[i]["steps"] for i in idx], float)
        dist = np.array([trials[i]["distance"] for i in idx], float)

        def err(est, truth):
            e = np.abs(np.array(est) - truth)
            return f"{e.mean():.1f}" + (f" ({100 * e.sum() / truth.sum():.1f}%)" if truth.sum() > 0 else "")
        lines.append(f"| {g} | {len(idx)} | {err([float(old[trials[i]['name']]['ankle_steps']) for i in idx], steps)} "
                     f"| {err([res_ankle[i]['steps_est'] for i in idx], steps)} "
                     f"| {err([float(old[trials[i]['name']]['ankle_m']) for i in idx], dist)} m "
                     f"| {err([res_ankle[i]['dist_est'] for i in idx], dist)} m |")
    return "\n".join(lines)


# ---- Main -------------------------------------------------------------------------------------------
def main():
    begin = time.time()
    trials = [load_trial(t) for t in good_trials()]
    n_clips = sum(len(clip_starts(tr)) for tr in trials)
    print(f"{len(trials)} good trials, {n_clips} clips")

    res_ankle, curves_ankle = leave_one_trial_out(trials, with_phone=False)
    res_both, curves_both = leave_one_trial_out(trials, with_phone=True)
    peaks = [peak_count(tr) for tr in trials]

    # Per-trial results
    with open(HERE / "results_per_trial.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trial", "activity", "true_steps", "ankle_steps", "ankle_steps_pm", "both_steps", "both_steps_pm",
                    "peak_steps", "true_m", "ankle_m", "ankle_m_pm", "both_m", "both_m_pm"])
        for tr, a, b, p in zip(trials, res_ankle, res_both, peaks):
            w.writerow([tr["name"], tr["activity"], tr["steps"], f"{a['steps_est']:.1f}", f"{a['steps_pm']:.1f}",
                        f"{b['steps_est']:.1f}", f"{b['steps_pm']:.1f}", p, tr["distance"],
                        f"{a['dist_est']:.1f}", f"{a['dist_pm']:.1f}", f"{b['dist_est']:.1f}", f"{b['dist_pm']:.1f}"])

    table = error_table(trials, res_ankle, res_both, peaks)
    unc = uncertainty_table(trials, res_ankle)
    # The 22-feature model's results, saved when the features changed, for comparison
    old_results = HERE / "results_per_trial_22features.csv"
    comparison = ""
    if FEATURE_SET != "combined" and old_results.exists():
        comparison = ("\n\n## Compared with the 22-feature model\n\n"
                      "The same leave-one-out test, ankle only, for the earlier model with the 12 per-axis features "
                      "as well (`step_model_22features.npz`, `results_per_trial_22features.csv`). Average error per "
                      "trial, and in brackets as a % of the true total.\n\n" + comparison_table(trials, res_ankle, old_results))
    # evaluate_tests.py adds a "Test walks" section at the end of results.md; keep it
    marker = "<!-- test walks: written by evaluate_tests.py -->"
    old = (HERE / "results.md").read_text() if (HERE / "results.md").exists() else ""
    kept = ("\n" + marker + old.split(marker, 1)[1]) if marker in old else ""
    with open(HERE / "results.md", "w") as f:
        f.write("# Step counter: leave-one-trial-out results\n\n"
                f"Written by `train_steps.py`, features: {FEATURE_SET} ({len(feature_names(False))} per sensor). "
                f"{len(trials)} good trials, {n_clips} clips of 2 s. Each trial's "
                f"totals come from a committee of {N_NETS} nets trained without it. Errors are the mean absolute "
                "error per trial, and in brackets the total error as a % of the true total. The +/- is the spread "
                "between the committee's nets.\n\n" + table + "\n\n"
                "## The +/- the dashboard shows\n\n"
                "From the ankle-only errors above (root-mean-square per group), not from the committee's "
                "spread, which is far smaller than the real errors. Saved in `step_model.npz`; the board "
                "picks the group from the net's own step rate for each clip and adds up `clip_uncertainty`.\n\n"
                + uncertainty_markdown(unc) + comparison + "\n" + kept)
    print("\n" + table + comparison)

    plot_losses({"Ankle only": curves_ankle, "Ankle + phone": curves_both}, MEDIA / "train_loss.png")
    plot_estimates(trials, res_ankle, res_both, peaks, MEDIA / "steps_est_vs_true.png")

    # The model for the UNO Q: the ankle-only committee, trained on every good trial
    X = np.vstack([trial_clips(tr, False)[0] for tr in trials])
    y = np.vstack([trial_clips(tr, False)[1] for tr in trials])
    nets = []
    for k in range(N_NETS):
        net, mean, std, _, _ = train_net(X, y, seed=k)
        nets.append((net, mean, std))
    save_for_board(nets, HERE / "step_model.npz", unc)
    shutil.copyfile(HERE / "step_model.npz", BOARD_MODEL)       # deploy.py sends uno_q/ to the board
    # Check the numpy version gives the same answers as PyTorch
    torch_avg = np.mean([predict(n, m, s, X) for n, m, s in nets], axis=0)
    numpy_avg, _ = numpy_predict(np.load(HERE / "step_model.npz"), X)
    print(f"\nSaved step_model.npz; numpy vs PyTorch, largest difference: {np.abs(torch_avg - numpy_avg).max():.2e}")
    print("\nThe dashboard's +/-:\n" + uncertainty_markdown(unc))
    print(f"Done in {(time.time() - begin) / 60:.1f} min")


if __name__ == "__main__":
    main()
