"""
Train the walk-straight policy with PPO (MJLab + RSL-RL) on this computer's CPU.

How it works: registers walk_straight_task with the chosen number of robots and
training rounds, then hands it to MJLab's own training loop (launch_training). Each
round, every robot takes 24 decisions (1.2 s of walking), then PPO updates the
policy. Checkpoints (model_<round>.pt, every 50 rounds and at the end) and
TensorBoard logs go to train/logs/rsl_rl/walk_straight/<date_time>_<name>/ (ignored by git).

Run from the HW8 folder:
  ../../.venv-mjlab/bin/python train/train.py --envs 256 --iters 300 --name first_check
Watch progress:
  ../../.venv-mjlab/bin/tensorboard --logdir train/logs/rsl_rl/walk_straight
"""

import argparse
import os
import sys
from pathlib import Path

TRAIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAIN_DIR))

from mjlab.scripts.train import TrainConfig, launch_training  # noqa: E402
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg  # noqa: E402
import walk_straight_task as T  # noqa: E402

parser = argparse.ArgumentParser(description="Train the HW8 walk-straight policy")
parser.add_argument("--envs", type=int, default=256, help="robots simulated side by side")
parser.add_argument("--iters", type=int, default=300, help="PPO training rounds")
parser.add_argument("--name", default="", help="label added to the run folder name")
parser.add_argument("--seed", type=int, default=42)
args = parser.parse_args()

os.environ["WANDB_MODE"] = "disabled"          # local logs only, nothing uploaded
task = T.register(num_envs=args.envs, max_iterations=args.iters)
agent = load_rl_cfg(task)
agent.run_name, agent.seed = args.name, args.seed
cfg = TrainConfig(env=load_env_cfg(task), agent=agent,
                  log_root=str(TRAIN_DIR / "logs" / "rsl_rl"), gpu_ids=None)
launch_training(task, cfg)
