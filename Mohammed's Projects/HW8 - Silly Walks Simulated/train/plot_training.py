"""
Plot a training run's progress from its TensorBoard log: is it learning?

How it works: MJLab/RSL-RL writes one data point per training round into the run's
TensorBoard event file. This reads those points and draws, per round:
  - total reward per episode (should go UP)
  - each reward term per episode: heading and drift penalties (should shrink toward 0),
    forward progress (should stay positive), flips
  - episode length (episodes end early only when robots flip)
  - the policy's exploration noise ("action std"; shrinks as it gets confident)
Note: the first rounds look odd because MJLab starts robots at random points within
their episodes; values settle once whole 20 s episodes are being completed.

Run from the HW8 folder:
  ../../.venv-mjlab/bin/python train/plot_training.py                 (newest run)
  ../../.venv-mjlab/bin/python train/plot_training.py --run <run folder>
Saves docs/media/training_<run name>.png
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

HW8 = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--run", help="run folder (default: newest walk_straight run)")
args = parser.parse_args()
run = Path(args.run) if args.run else sorted(
    (HW8 / "train" / "logs" / "rsl_rl" / "walk_straight").glob("*/"))[-1]
ea = EventAccumulator(str(run), size_guidance={"scalars": 0})
ea.Reload()


def series(tag):
    ev = ea.Scalars(tag)
    return [e.step for e in ev], [e.value for e in ev]


panels = [
    ("Total reward per episode (higher = better)", ["Train/mean_reward"]),
    ("Straightness penalties per episode (closer to 0 = straighter)",
     ["Episode_Reward/heading", "Episode_Reward/drift"]),
    ("Forward progress per episode", ["Episode_Reward/forward"]),
    ("Flip penalty and jerk penalty per episode", ["Episode_Reward/flip", "Episode_Reward/jerk"]),
    ("Episode length (decisions; 400 = full 20 s)", ["Train/mean_episode_length"]),
    ("Exploration noise (action std)", ["Policy/mean_std"]),
]
fig, axes = plt.subplots(3, 2, figsize=(12, 10))
for ax, (title, tags) in zip(axes.ravel(), panels):
    for tag in tags:
        if tag in ea.Tags()["scalars"]:
            x, y = series(tag)
            ax.plot(x, y, label=tag.split("/")[-1])
    ax.set(title=title, xlabel="training round")
    ax.grid(alpha=0.3)
    if len(tags) > 1:
        ax.legend()
fig.suptitle(f"Training run {run.name}")
fig.tight_layout()
out = HW8 / "docs" / "media" / f"training_{run.name}.png"
fig.savefig(out, dpi=110)
x, y = series("Train/mean_reward")
print(f"{run.name}: {len(x)} rounds, mean reward {y[0]:.2f} -> {y[-1]:.2f}\nSaved {out.relative_to(HW8)}")
