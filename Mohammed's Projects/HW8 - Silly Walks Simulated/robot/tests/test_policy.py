"""
Proof that the exported policy (robot/policy.py, numpy only) gives the same actions as the
policy did inside MJLab.

How it works: training_reference.npz holds 800 inputs the policy saw in the training
environment and the actions MJLab's policy chose for them (recorded by
train/export_policy.py). This feeds the same inputs to robot/policy.py and compares.
Also checks the input size matches policy_meta.json.

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_policy.py
"""

import sys
from pathlib import Path

import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))
import units as U  # noqa: E402
from policy import Policy  # noqa: E402

ref = np.load(ROBOT_DIR / "tests" / "data" / "training_reference.npz")
obs, act = ref["obs"].reshape(-1, 16), ref["action"].reshape(-1, 2)
out = Policy()(obs)
diff = np.abs(out - act).max()
one_by_one = np.abs(np.stack([Policy()(o) for o in obs[:20]]) - act[:20]).max()
checks = [
    (f"input size is {U.OBS_SIZE}, as in policy_meta.json", obs.shape[1] == U.OBS_SIZE),
    (f"numpy policy = MJLab policy on {len(obs)} recorded inputs (max diff {diff:.1e})", diff < 1e-5),
    (f"same when called one input at a time, as the control loop does (max diff {one_by_one:.1e})",
     one_by_one < 1e-5),
]
for text, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")
print(f"{sum(ok for _, ok in checks)}/{len(checks)} checks passed")
sys.exit(0 if all(ok for _, ok in checks) else 1)
