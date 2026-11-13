"""
The trained policy, runnable with numpy alone (no MJLab, no TorchScript).

How it works: train/export_policy.py saved the actor network's numbers to
robot/model/policy_weights.npz. The network is small, so it is written out by hand:

    x = (obs - mean) / (std + 0.01)       input scaling learned during training
    h1 = ELU(W0 x + b0)                   16 -> 64
    h2 = ELU(W1 h1 + b1)                  64 -> 64
    action = W2 h2 + b2                   64 -> 2   (right leg, left leg)

ELU(x) = x for x > 0, e^x - 1 otherwise. The output is the policy's chosen action (the
mean of its exploration distribution; no randomness when driving). tests/test_policy.py
checks this gives the same actions as MJLab did during a recorded training-environment run.
(robot/model/policy.pt is the same network as TorchScript, kept as a backup; PyTorch warns
that TorchScript loading is not supported on Python 3.14, so it is not used here.)
"""

import numpy as np

from units import MODEL_DIR, OBS_SIZE


class Policy:
    def __init__(self, path=MODEL_DIR / "policy_weights.npz"):
        w = np.load(path)
        self.mean, self.scale = w["obs_mean"], w["obs_std"] + w["obs_eps"]
        self.layers = [(w["w0"], w["b0"]), (w["w1"], w["b1"]), (w["w2"], w["b2"])]
        assert self.mean.shape == (OBS_SIZE,), "policy input size does not match policy_meta.json"

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        """obs: 16 numbers (or a batch [n, 16]) -> action (2,) or [n, 2]."""
        x = (np.asarray(obs, dtype=np.float64) - self.mean) / self.scale
        for i, (W, b) in enumerate(self.layers):
            x = x @ W.T + b
            if i < len(self.layers) - 1:
                x = np.where(x > 0, x, np.expm1(x))      # ELU
        return x
