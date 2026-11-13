"""
Sanity check of the walk-straight reward BEFORE training: do scripted behaviours
score the way we intend? (About 1 minute.)

How it works: builds the real task with 16 robots and drives them with fixed,
hand-written commands for a whole 20 s episode (no learning). It adds up each
robot's reward and also each reward term separately (per second), and counts flips.

Scenarios:
  A  perfect-twin robots, legs in step, same speed           -> should score well
  A2 perfect twins but legs OUT of step                      -> turns, scores lower
  B  standing still (both legs stopped)                     -> must score below A
  C  BADLY OFF COURSE: same as A but told its start direction was 45 deg to the
     side, so it is off course for the whole episode         -> continuing must still
     score better than flipping on purpose (-75 + what it earned before the flip)
  D  lopsided robots (full randomization), same speed both legs -> below A (drifts)
  E  jerky random commands every decision                    -> the jerk penalty stays small
It also prints the guaranteed worst case: the lowest possible continuing score for a
whole episode, which must be above -FLIP_PENALTY.

Run from the HW8 folder:  ../../.venv-mjlab/bin/python train/reward_check.py
"""

import math
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mjlab.envs import ManagerBasedRlEnv  # noqa: E402
import walk_straight_task as T  # noqa: E402

N = 16
STEPS = round(T.EPISODE_S / T.DECISION_DT) - 1    # stop one step before the time-out reset


def run(name, command, randomize, yaw_offset_deg=0.0, in_step=False):
    cfg = T.make_env_cfg(num_envs=N)
    if not randomize:      # keep only the basic reset: perfect twins, default friction/mass
        cfg.events = {"reset_robot": cfg.events["reset_robot"]}
    cfg.events["reset_robot"].params = {"legs_in_step": in_step}
    env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
    env.reset()
    action_term = env.action_manager.get_term("leg_speed")
    if not randomize:
        action_term.motor_scale[:] = 1.0
    if yaw_offset_deg:
        T._state(env)["start_yaw"] += math.radians(yaw_offset_deg)

    names = env.reward_manager.active_terms
    total = torch.zeros(N)
    per_term = torch.zeros(N, len(names))
    alive = torch.ones(N, dtype=torch.bool)
    flip_step = torch.full((N,), -1)
    for k in range(STEPS):
        a = command(k)
        _, rew, terminated, _, _ = env.step(a)
        # count rewards only while the robot is still in its first episode
        total += torch.where(alive, rew, torch.zeros_like(rew))
        per_term += torch.where(alive[:, None], env.reward_manager._step_reward * env.step_dt, 0.0)
        newly = alive & terminated
        flip_step[newly] = k
        alive &= ~terminated
    env.close()
    secs = STEPS * T.DECISION_DT
    terms = "  ".join(f"{n} {per_term[:, i].mean() / secs:+.2f}/s" for i, n in enumerate(names))
    print(f"{name:42} return {total.mean():+7.1f} (min {total.min():+6.1f})  flips {int((flip_step >= 0).sum())}/{N}\n"
          f"   -> per term: {terms}", flush=True)
    return total


const = lambda c: (lambda k: torch.full((N, 2), c))
print(f"Episode {T.EPISODE_S:.0f} s, {N} robots per scenario, flip penalty -{T.FLIP_PENALTY:.0f}\n")
A = run("A twins, legs in step, 60 rpm (ideal)", const(0.0), randomize=False, in_step=True)
A2 = run("A2 twins, legs OUT of step, 60 rpm", const(0.0), randomize=False)
B = run("B standing still", const(-1.0), randomize=False)
C = run("C off course by 45 deg the whole episode", const(0.0), randomize=False, yaw_offset_deg=45, in_step=True)
D = run("D lopsided robots, 60 rpm (full randomization)", const(0.0), randomize=True)
E = run("E jerky random commands (twins)", lambda k: torch.rand(N, 2) * 2 - 1, randomize=False)

worst_per_s = 0.0 - T.W_HEADING * T.HEADING_CAP - T.W_DRIFT * T.DRIFT_CAP - T.W_JERK * 8
worst_episode = worst_per_s * T.EPISODE_S
print("\nCHECKS")
checks = [
    ("standing still scores below walking straight (B < A)", B.mean() < A.mean()),
    ("lopsided equal-speed robots score below twins (D < A)", D.mean() < A.mean()),
    ("out-of-step twins score below in-step twins (A2 < A)", A2.mean() < A.mean()),
    (f"off course (C) still beats flipping at once (-{T.FLIP_PENALTY:.0f})", C.min() > -T.FLIP_PENALTY),
    (f"guaranteed worst continuing episode {worst_episode:.1f} > -{T.FLIP_PENALTY:.0f} flip", worst_episode > -T.FLIP_PENALTY),
]
for text, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")
