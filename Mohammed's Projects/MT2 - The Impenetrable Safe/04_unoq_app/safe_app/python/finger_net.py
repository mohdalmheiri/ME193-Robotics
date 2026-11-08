"""
finger_net.py - the trained finger-counting network, in plain numpy.

Why not PyTorch on the board: PyTorch is a ~1 GB install, and the board's
OpenCV can't run ONNX files. But the network is small (3 convolutions and
one linear layer, see 03_training/model.py), so the same arithmetic fits in
a few lines of numpy, which the board already has. The trained numbers come
from finger_cnn.pt, exported to finger_net.npz by prepare_board_files.py.

Same math as model.py:
    photo 3x128x128 -> conv 3x3 (8)  -> ReLU -> max pool -> 8x64x64
                    -> conv 3x3 (16) -> ReLU -> max pool -> 16x32x32
                    -> conv 3x3 (32) -> ReLU -> max pool -> 32x16x16
                    -> flatten (8192) -> linear -> 6 scores
prepare_board_files.py checks that this gives the same answers as PyTorch.
"""
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

HERE = Path(__file__).resolve().parent


def conv3x3(x, w, b):
    """One convolution layer with a 1-pixel border (padding=1), like nn.Conv2d(..., 3, padding=1).

    x: (channels_in, H, W).  w: (channels_out, channels_in, 3, 3).  b: (channels_out,).
    Every output pixel is the sum of a 3x3 patch (in every input channel)
    times the filter's 3x3 weights, plus the bias.
    """
    xp = np.pad(x, ((0, 0), (1, 1), (1, 1)))                   # the 1-pixel border of zeros
    patches = sliding_window_view(xp, (3, 3), axis=(1, 2))     # (C, H, W, 3, 3): every 3x3 patch, no copying
    out = np.tensordot(w, patches, axes=([1, 2, 3], [0, 3, 4]))  # multiply and add -> (channels_out, H, W)
    return out + b[:, None, None]


def relu(x):
    return np.maximum(x, 0)                                     # keep positive "found it" signals only


def maxpool2(x):
    """Keep the largest of each 2x2 block: halves the width and height."""
    c, h, w = x.shape
    return x.reshape(c, h // 2, 2, w // 2, 2).max(axis=(2, 4))


class FingerNet:
    def __init__(self, path=HERE / "finger_net.npz"):
        p = np.load(path)
        self.layers = [(p[f"conv{i}.weight"], p[f"conv{i}.bias"]) for i in (1, 2, 3)]
        self.fc_w, self.fc_b = p["fc.weight"], p["fc.bias"]

    def scores(self, x):
        """x: one photo from hand_crop.to_network_input, shape (3, 128, 128). Returns 6 raw scores."""
        for w, b in self.layers:
            x = maxpool2(relu(conv3x3(x, w, b)))
        return self.fc_w @ x.reshape(-1) + self.fc_b            # flatten in the same order as PyTorch

    def guess(self, x):
        """Returns (best count 0..5, its confidence 0..1, all six confidences)."""
        s = self.scores(x)
        e = np.exp(s - s.max())                                 # softmax: scores -> confidences adding up to 1
        probs = e / e.sum()
        best = int(probs.argmax())
        return best, float(probs[best]), probs
