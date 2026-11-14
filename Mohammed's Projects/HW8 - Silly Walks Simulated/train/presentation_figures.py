"""
Presentation figures (class demo, Notion): large fonts, one message per figure, the same
colors everywhere (baseline orange, simple controller green-aqua, policy blue).

  1_three_drivers.png    baseline vs simple controller vs v2 policy: heading error, sideways
                         drift, distance walked (100 MJLab robots, 20 s)
  2_tipping_fix.png      flips in 100 robots, v1 vs v2, in the training simulator and in FakeRobot
  3_training_curve.png   v2's training: total reward and heading penalty over 800 rounds
  4_paths_100_robots.png every robot's path from above, one panel per driver

Data (nothing is re-simulated here):
  - docs/data/eval_v2_dt0.002_paths.npz  from  train/evaluate.py --task v2 ... --save-paths
    (the same run as docs/eval_results_v2_dt0.002.md; this script checks that the numbers
    match that table before drawing)
  - flips: the RECORDED numbers, with their sources written on the figure:
      v1 FakeRobot  docs/fake_robot_check.md at commit 445323c (6 of 100 with the encoder leg
                    speed, 9 of 100 with the hub speed v1 trained on)
      v2 FakeRobot  docs/fake_robot_check.md now (1 of 100, either leg-speed input)
      MJLab         docs/eval_results_dt0.002.md (v1) and docs/eval_results_v2_dt0.002.md (v2): 0 and 0
  - training: the v2 run's TensorBoard log in train/logs/ (not in git)
Colors: the first three slots of a palette validated for color-blind separation (all pairs),
with every bar and panel also labeled in text, so color is never the only cue.

Run from the HW8 folder (tensorboard is in the MJLab environment):
  ../../.venv-mjlab/bin/python train/presentation_figures.py
Saves docs/media/presentation/*.png (1920 x 1080).
"""

import re
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HW8 = Path(__file__).resolve().parent.parent
OUT = HW8 / "docs" / "media" / "presentation"
OUT.mkdir(parents=True, exist_ok=True)
NPZ = HW8 / "docs" / "data" / "eval_v2_dt0.002_paths.npz"
EVAL_MD = HW8 / "docs" / "eval_results_v2_dt0.002.md"
RUN = HW8 / "train" / "logs" / "rsl_rl" / "walk_straight_v2" / "2026-11-13_18-36-30_v2"

# colors (validated palette, light mode) and text inks
COL = {"baseline": "#eb6834", "controller": "#1baf7a", "policy": "#2a78d6", "v1": "#8a8985"}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
NAMES = {"baseline": "Baseline\n(both motors one speed)", "controller": "Simple controller\n(steers by heading)",
         "policy": "Trained policy\n(v2)"}
plt.rcParams.update({
    "font.size": 20, "axes.titlesize": 22, "axes.labelsize": 20, "xtick.labelsize": 18,
    "ytick.labelsize": 18, "legend.fontsize": 18, "figure.titlesize": 30,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1.0, "axes.axisbelow": True,
})
SIZE, DPI = (16, 9), 120                       # 1920 x 1080


def title(fig, main, sub):
    """Bold title (one line, the figure's message) and a wrapped grey subtitle under it."""
    fig.suptitle(main, x=0.03, ha="left", va="top", y=0.97, fontweight="bold", fontsize=30)
    fig.text(0.03, 0.89, "\n".join(textwrap.wrap(" ".join(sub.split()), 112)), ha="left", va="top",
             fontsize=18, color=INK2, linespacing=1.3)


def source(fig, text):
    """Small grey source note at the bottom, wrapped to the figure width."""
    fig.text(0.03, 0.015, "\n".join(textwrap.wrap(" ".join(text.split()), 150)), ha="left", va="bottom",
             fontsize=13, color=INK2, linespacing=1.3)


def save(fig, name):
    fig.savefig(OUT / name, dpi=DPI)
    plt.close(fig)
    print(f"saved docs/media/presentation/{name}")


# ------------------------------------------------------------------ data + consistency check
D = np.load(NPZ)
DRV = ("baseline", "controller", "policy")
stats = {}
for k in DRV:
    stats[k] = {"head": np.abs(D[f"{k}_head"]), "side": np.abs(D[f"{k}_side"]), "fwd": D[f"{k}_fwd"],
                "flips": int(D[f"{k}_flipped"].sum())}
# the numbers must be those of the committed evaluation table (same run, same robots)
md = EVAL_MD.read_text()
for label, key in (("Sideways drift", "side"), ("Heading error", "head"), ("Forward distance", "fwd")):
    row = next(l for l in md.splitlines() if l.startswith(f"| {label}"))      # noqa: E741
    cells = row.split("|")[2:5]
    for k, cell in zip(DRV, cells):
        mean_md = float(re.findall(r"-?\d+", cell)[0])
        mean_now = stats[k][key].mean()
        assert abs(mean_now - mean_md) <= 0.5, f"{k} {key}: npz {mean_now:.1f} vs table {mean_md}"
print("npz matches docs/eval_results_v2_dt0.002.md")
K = float(D["K"])

# ------------------------------------------------------------------ 1. three drivers
fig, axes = plt.subplots(1, 3, figsize=SIZE)
fig.subplots_adjust(left=0.06, right=0.98, top=0.68, bottom=0.17, wspace=0.35)
panels = (("head", "Heading error (deg)", "lower is better", "{:.0f}°"),
          ("side", "Sideways drift (mm)", "lower is better", "{:.0f}"),
          ("fwd", "Distance walked in 20 s (mm)", "higher is better", "{:.0f}"))
x = np.arange(3)
for ax, (key, ylabel, better, f) in zip(axes, panels):
    means = [stats[k][key].mean() for k in DRV]
    ax.bar(x, means, width=0.62, color=[COL[k] for k in DRV], edgecolor=SURFACE, linewidth=2)
    for xi, m in zip(x, means):
        ax.text(xi, m, f.format(m), ha="center", va="bottom", fontsize=22, fontweight="bold",
                color=INK)
    ax.set_xticks(x, ["Baseline", "Controller", "Policy"])
    ax.set_title(f"{ylabel}\n({better})", loc="left", fontsize=20)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, max(means) * 1.18)
title(fig, "Both steer straight; the policy walks 1.9× farther",
      f"100 randomly lopsided robots in the training simulator (MJLab), 20 s each, same robots for all three. "
      f"Bars: mean.\nController: right = c − K·h, left = c + K·h on the same noisy heading input, "
      f"K = {K:g} tuned on 100 other robots. The controller steers by nearly stopping one leg, which costs distance.")
source(fig, "Source: train/evaluate.py --task v2 → docs/eval_results_v2_dt0.002.md (checkpoint walk_straight_v2/"
            "2026-11-13_18-36-30_v2/model_799.pt); medians and worst 5 % are in that table.")
save(fig, "1_three_drivers.png")

# ------------------------------------------------------------------ 2. tipping fix (recorded numbers)
fig, ax = plt.subplots(figsize=SIZE)
fig.subplots_adjust(left=0.08, right=0.97, top=0.72, bottom=0.25)
groups = ["Training simulator\n(MJLab)", "FakeRobot\n(same robot, slightly different but valid physics)"]
v1 = [0, 9]                       # MJLab 0; FakeRobot 6 (encoder) - 9 (hub speed)
v2 = [0, 1]
w = 0.34
gx = np.arange(2)
ax.bar(gx - w / 2 - 0.01, v1, width=w, color=COL["v1"], edgecolor=SURFACE, linewidth=2, label="v1 policy")
ax.bar(gx + w / 2 + 0.01, v2, width=w, color=COL["policy"], edgecolor=SURFACE, linewidth=2, label="v2 policy")
for xi, txt, y in ((gx[0] - w / 2, "0", 0), (gx[0] + w / 2, "0", 0), (gx[1] - w / 2, "6–9 *", 9),
                   (gx[1] + w / 2, "1", 1)):
    ax.text(xi, y + 0.15, txt, ha="center", va="bottom", fontsize=26, fontweight="bold")
for xi, name in ((gx[0] - w / 2, "v1"), (gx[0] + w / 2, "v2"), (gx[1] - w / 2, "v1"), (gx[1] + w / 2, "v2")):
    ax.text(xi, -0.35, name, ha="center", va="top", fontsize=20, color=INK2)
ax.set_xticks(gx, groups)
ax.tick_params(axis="x", pad=40)
ax.set_ylabel("Robots that flipped (of 100)")
ax.set_ylim(0, 11)
ax.grid(axis="x", visible=False)
ax.legend(loc="upper left", frameon=False)
title(fig, "v2 fixed the tipping: 1 flip in 100 robots instead of 6–9",
      "Both policies never flipped in the simulator they trained in. In FakeRobot (the robot-side "
      "check, physics set up independently)\nv1 tipped 6–9 robots in 100: it kept too little margin. "
      "v2 trained with wider physics randomization (motor inertia, joint friction, contact stiffness, "
      "mass), random pushes and a penalty for tilting past 40°.")
source(fig, "Recorded numbers, 100 lopsided robots, 20 s each. * v1: 6 with the encoder leg speed, 9 with the "
            "hub speed v1 trained on — docs/fake_robot_check.md at commit 445323c (2026-11-13).\n"
            "v2: 1 with either leg-speed input — docs/fake_robot_check.md (2026-11-14). MJLab: "
            "docs/eval_results_dt0.002.md (v1), docs/eval_results_v2_dt0.002.md (v2).")
save(fig, "2_tipping_fix.png")

# ------------------------------------------------------------------ 3. training curve
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator  # noqa: E402

ea = EventAccumulator(str(RUN), size_guidance={"scalars": 0})
ea.Reload()


def series(tag):
    s = ea.Scalars(tag)
    return np.array([p.step for p in s]), np.array([p.value for p in s])


def smooth(y, n=15):
    """Centered moving average (the raw curve is drawn faint behind it)."""
    k = np.ones(n) / n
    pad = np.pad(y, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(pad, k, mode="valid")


r_x, r_y = series("Train/mean_reward")
h_x, h_y = series("Episode_Reward/heading")
f_x, f_y = series("Episode_Termination/flipped")
_, fw_y = series("Episode_Reward/forward")
fw_100, fw_end = fw_y[90:110].mean(), fw_y[-15:].mean()       # forward progress at round ~100 and at the end
fig, axes = plt.subplots(1, 2, figsize=SIZE)
fig.subplots_adjust(left=0.07, right=0.97, top=0.68, bottom=0.17, wspace=0.25)
for ax, x_, y_, ttl in ((axes[0], r_x, r_y, "Total reward (higher = better)"),
                        (axes[1], h_x, h_y, "Heading penalty (closer to 0 = straighter)")):
    ax.plot(x_, y_, color=COL["policy"], lw=1, alpha=0.3)
    ax.plot(x_, smooth(y_), color=COL["policy"], lw=3)
    ax.set_title(ttl, loc="left", fontsize=20)
    ax.set_xlabel("Training round")
    ax.set_xlim(0, x_[-1])
    ax.axvline(x_[-1], color=INK2, lw=1.5, ls="--")
    ax.text(x_[-1] - 10, ax.get_ylim()[0] + 0.05 * np.ptp(ax.get_ylim()), "exported:\nround 799",
            ha="right", va="bottom", fontsize=16, color=INK2)
axes[0].annotate(f"{r_y[-1]:.1f}", (r_x[-1], r_y[-1]), xytext=(-60, 15), textcoords="offset points",
                 fontsize=20, fontweight="bold")
title(fig, "v2 training: straight within ~100 rounds, then faster",
      f"PPO in MJLab, 800 rounds, randomly lopsided robots. Faint: every round; bold: 15-round average. "
      f"No robot flipped in any round (flip terminations: {int(f_y.max())} in all {len(f_x)} rounds). "
      "The heading penalty levels off by round ~100; the reward keeps rising because the robots walk farther "
      f"(forward-progress reward per episode {fw_100:.2f} at round ~100 → {fw_end:.2f} at the end). The first ~25 rounds look odd: episodes start at random "
      "points until full 20 s episodes complete.")
source(fig, "Source: TensorBoard log of train/logs/rsl_rl/walk_straight_v2/2026-11-13_18-36-30_v2 "
            "(Train/mean_reward, Episode_Reward/heading, Episode_Reward/forward, Episode_Termination/flipped).")
save(fig, "3_training_curve.png")

# ------------------------------------------------------------------ 4. paths, 100 robots
fig, axes = plt.subplots(1, 3, figsize=SIZE, sharex=True, sharey=True)
fig.subplots_adjust(left=0.09, right=0.98, top=0.68, bottom=0.21, wspace=0.08)
for ax, k in zip(axes, DRV):
    xy = D[f"{k}_xy"]
    for i in range(xy.shape[0]):
        ax.plot(xy[i, :, 0], xy[i, :, 1], color=COL[k], lw=1.2, alpha=0.45)
    ax.scatter(xy[:, -1, 0], xy[:, -1, 1], s=22, color=COL[k], edgecolor=SURFACE, linewidth=0.8, zorder=3)
    ax.axvline(0, color=INK, lw=1.8, ls=(0, (6, 4)))
    ax.axhline(0, color=INK2, lw=1.2)
    s = stats[k]
    ax.set_title(f"{NAMES[k].splitlines()[0]}\nheading {s['head'].mean():.0f}° · drift {s['side'].mean():.0f} mm"
                 f"\nwalked {s['fwd'].mean():.0f} mm · flips {s['flips']}", loc="left", fontsize=18)
    ax.set_xlabel("Sideways (mm, + = right)")
    ax.set_aspect("equal", adjustable="box")
axes[0].set_ylabel("Forward (mm)")
axes[0].plot([], [], color=INK, lw=1.8, ls=(0, (6, 4)), label="straight ahead from the start")
axes[0].scatter([], [], s=40, color=INK2, label="where each robot ended")
fig.legend(loc="lower right", bbox_to_anchor=(0.98, 0.035), frameon=False, ncol=2, fontsize=16)
title(fig, "100 lopsided robots, 20 s each, seen from above",
      "Every line is one robot starting at (0, 0) facing up. Same 100 robots for all three drivers "
      "(training simulator, MJLab). Numbers: means.")
source(fig, "Source: train/evaluate.py --task v2 --save-paths → docs/data/eval_v2_dt0.002_paths.npz "
            "(the run in docs/eval_results_v2_dt0.002.md).")
save(fig, "4_paths_100_robots.png")
