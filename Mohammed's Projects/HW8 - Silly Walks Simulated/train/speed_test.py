"""
How fast can MJLab simulate and train the HW8 robot on this Mac's CPU?

Part 1, simulation speed: for each physics step size and each number of robots
  simulated side by side (num_envs), build the task, warm up (Warp compiles its CPU
  code the first time, which must not count), then feed random motor commands for
  SECONDS and count steps. Two speeds are reported:
    - policy steps/s:  robot-decisions per second (one per robot every 0.02 s of sim time).
                       This is the number RL training "consumes".
    - physics steps/s: policy steps x decimation (MuJoCo steps per decision).
  The CPU load (process CPU time / wall time) shows whether all 8 cores are used.

Part 2, real training: runs MJLab's normal PPO training on the placeholder task for
  a fixed small number of iterations (chosen to take about 1.5 minutes), and times it.
  One iteration = every robot takes 24 policy steps, then PPO updates the networks.
  Logs go to train/logs/ (ignored by git).

Run from the HW8 folder with the MJLab environment:
  ../../.venv-mjlab/bin/python train/speed_test.py              # both parts
  ../../.venv-mjlab/bin/python train/speed_test.py --part 1
"""

import argparse
import os
import resource
import sys
import time
from pathlib import Path

import torch

TRAIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAIN_DIR))

from mjlab.envs import ManagerBasedRlEnv  # noqa: E402
from speedtest_task import make_env_cfg, register  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--part", type=int, choices=(1, 2), help="run only part 1 or 2")
parser.add_argument("--seconds", type=float, default=12.0, help="timed seconds per part-1 case")
parser.add_argument("--train-envs", type=int, default=256, help="num_envs for part 2")
parser.add_argument("--train-dt", type=float, default=0.002, help="physics step for part 2")
parser.add_argument("--train-iters", type=int, default=20, help="PPO iterations for part 2")
args = parser.parse_args()


def cpu_seconds():
    """CPU time used by this process so far (all threads added up)."""
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def measure(dt, num_envs):
    cfg = make_env_cfg(timestep=dt, num_envs=num_envs)
    env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
    env.reset()
    act = lambda: torch.rand(num_envs, 2) * 2 - 1      # random commands in -1..1
    for _ in range(5):                                   # warm-up (compilation, caches)
        env.step(act())
    steps, t0, c0 = 0, time.perf_counter(), cpu_seconds()
    while time.perf_counter() - t0 < args.seconds:
        env.step(act())
        steps += 1
    wall, cpu = time.perf_counter() - t0, cpu_seconds() - c0
    env.close()
    policy_sps = steps * num_envs / wall
    return policy_sps, policy_sps * cfg.decimation, cpu / wall


if args.part in (None, 1):
    print("\nPART 1: simulation speed (random motor commands)")
    print(f"{'step':>7} {'robots':>7} | {'policy steps/s':>14} {'physics steps/s':>16} | CPU cores busy")
    for dt in (0.002, 0.001):
        for n in (64, 256, 1024):
            p, s, load = measure(dt, n)
            print(f"{dt:7.3f} {n:7d} | {p:14,.0f} {s:16,.0f} | {load:5.1f}", flush=True)

if args.part in (None, 2):
    from mjlab.scripts.train import TrainConfig, launch_training
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg

    task = register(timestep=args.train_dt, num_envs=args.train_envs)
    agent = load_rl_cfg(task)
    agent.max_iterations = args.train_iters
    cfg = TrainConfig(env=load_env_cfg(task), agent=agent,
                      log_root=str(TRAIN_DIR / "logs" / "rsl_rl"), gpu_ids=None)
    os.environ["WANDB_MODE"] = "disabled"                # belt and braces: no uploads
    steps = args.train_iters * agent.num_steps_per_env * args.train_envs
    print(f"\nPART 2: PPO training, {args.train_envs} robots, step {args.train_dt}s, "
          f"{args.train_iters} iterations = {steps:,} policy steps")
    t0, c0 = time.perf_counter(), cpu_seconds()
    launch_training(task, cfg)
    wall, cpu = time.perf_counter() - t0, cpu_seconds() - c0
    print(f"\nPART 2 RESULT: {wall:.1f} s wall time, {steps / wall:,.0f} policy steps/s "
          f"(including PPO updates and setup), CPU cores busy {cpu / wall:.1f}")
