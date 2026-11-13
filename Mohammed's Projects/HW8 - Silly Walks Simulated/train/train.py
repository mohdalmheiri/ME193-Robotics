"""
Train the walk-straight policy with PPO (MJLab + RSL-RL) on this computer's CPU.

How it works: registers walk_straight_task with the chosen number of robots and
training rounds, then hands it to MJLab's own training loop (launch_training). Each
round, every robot takes 24 decisions (1.2 s of walking), then PPO updates the
policy. Checkpoints (model_<round>.pt, every 50 rounds and at the end) and
TensorBoard logs go to train/logs/rsl_rl/walk_straight/<date_time>_<name>/ (ignored by git).

Run from the HW8 folder:
  ../../.venv-mjlab/bin/python train/train.py --envs 256 --iters 300 --name first_check
  ../../.venv-mjlab/bin/python train/train.py --task v2 --iters 800 --name v2   (logs in
      train/logs/rsl_rl/walk_straight_v2/...)
Continue an earlier run instead of starting from scratch (keeps everything it learned):
  ../../.venv-mjlab/bin/python train/train.py --iters 500 --name longer_run \
      --resume 2026-11-12_22-50-21_first_check --checkpoint model_299.pt
  The new rounds are numbered on from the checkpoint (300, 301, ...) and saved in a NEW
  run folder; the old run is left untouched.
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
import walk_straight_task as T1  # noqa: E402
import walk_straight_v2_task as T2  # noqa: E402

parser = argparse.ArgumentParser(description="Train the HW8 walk-straight policy")
parser.add_argument("--task", choices=["v1", "v2"], default="v1",
                    help="v1 = walk_straight_task.py, v2 = walk_straight_v2_task.py")
parser.add_argument("--envs", type=int, default=256, help="robots simulated side by side")
parser.add_argument("--iters", type=int, default=300, help="PPO training rounds")
parser.add_argument("--name", default="", help="label added to the run folder name")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--resume", default=None,
                    help="run folder name (inside train/logs/rsl_rl/walk_straight) to continue from")
parser.add_argument("--checkpoint", default=None,
                    help="checkpoint file in that run, e.g. model_299.pt (required with --resume:"
                         " MJLab would otherwise pick the ALPHABETICALLY last file, model_50.pt)")
args = parser.parse_args()

os.environ["WANDB_MODE"] = "disabled"          # local logs only, nothing uploaded
T = T2 if args.task == "v2" else T1
task = T.register(num_envs=args.envs, max_iterations=args.iters)
agent = load_rl_cfg(task)
agent.run_name, agent.seed = args.name, args.seed
if args.resume:
    if not args.checkpoint:
        parser.error("--resume needs --checkpoint (e.g. model_299.pt)")
    # MJLab's training loop sees resume=True, finds <load_run>/<load_checkpoint> in the
    # experiment folder, and loads the network weights, the optimizer state and the
    # round counter before training goes on. "--iters" then means "this many MORE rounds".
    agent.resume = True
    agent.load_run = args.resume                 # MJLab treats both as patterns; plain
    agent.load_checkpoint = args.checkpoint      # names match exactly themselves
cfg = TrainConfig(env=load_env_cfg(task), agent=agent,
                  log_root=str(TRAIN_DIR / "logs" / "rsl_rl"), gpu_ids=None)
launch_training(task, cfg)
