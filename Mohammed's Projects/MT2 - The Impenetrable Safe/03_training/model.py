"""
model.py - the finger-counting network, in one place.

train.py, live_test.py, feature_maps.py (and later the UNO Q app) all import
it from here, so they always build exactly the same network.

The shape follows the professor's hint: three convolution layers, each
followed by ReLU and max pooling, then one linear layer with 6 outputs.

    photo 3 x 128 x 128  (blue, green, red; values 0..1)
      conv1: 8 filters, 3x3   -> ReLU -> max pool 2x2 ->  8 x 64 x 64
      conv2: 16 filters, 3x3  -> ReLU -> max pool 2x2 -> 16 x 32 x 32
      conv3: 32 filters, 3x3  -> ReLU -> max pool 2x2 -> 32 x 16 x 16
      flatten to 8192 numbers -> linear -> 6 scores, one per class 0..5

In plain words:
  * A convolution "filter" is a small 3x3 pattern detector that slides over
    the whole picture and lights up wherever its pattern appears. The first
    layer's filters find simple things (edges, skin against wood, the red
    tape). The next layers combine those into bigger shapes (a finger edge,
    a fingertip, a gap between fingers).
  * ReLU keeps only the positive "I found it" signals (as in the warm-up).
  * Max pooling keeps the strongest signal in each 2x2 patch and halves the
    picture's width and height. This makes the network care less about the
    exact pixel a finger is on, and makes each later layer cheaper.
  * The filter counts double (8 -> 16 -> 32) while the picture shrinks:
    fewer, bigger pixels but more kinds of pattern, a common balance.
  * The final linear layer weighs all 8192 numbers into 6 scores. The highest
    score is the guess; softmax turns the scores into confidences that add to 100%.

Why this small: about 55,000 numbers (weights) in total (about 220 KB), and
about 13 million multiply-adds per photo. That is light for the UNO Q's
processor (a guess would take milliseconds, not seconds), and a small network
is also less able to simply memorize 385 training photos.
"""
import torch
from torch import nn

CLASSES = ["0", "1", "2", "3", "4", "5"]   # class index i means "i fingers" (0 = fist or empty square)


class FingerCNN(nn.Module):
    def __init__(self):
        super().__init__()
        # padding=1 adds a 1-pixel border so a 3x3 filter keeps the picture the same size;
        # only the pooling shrinks it.
        self.conv1 = nn.Conv2d(3, 8, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(8, 16, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(16, 32, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2)                  # 2x2 -> 1, keeping the largest
        self.relu = nn.ReLU()
        self.fc = nn.Linear(32 * 16 * 16, len(CLASSES))

        # Starting values. With PyTorch's default start, 18 of the 32 layer-3 filters
        # ended up "dead": switched off (output 0) for every photo, so they got no
        # gradient and never learned, the same trap as the stuck neurons in the
        # warm-up. Two changes keep every filter alive:
        #   * Kaiming starting weights: random weights sized for ReLU networks, so
        #     the signal neither fades away nor blows up from layer to layer.
        #   * A small positive bias (0.1): every filter starts slightly switched on,
        #     so it gets a gradient from the first step.
        # Result: 0 dead filters instead of 1 / 2 / 18, with the same validation accuracy.
        for conv in (self.conv1, self.conv2, self.conv3):
            nn.init.kaiming_normal_(conv.weight, nonlinearity="relu")
            nn.init.constant_(conv.bias, 0.1)

    def forward(self, x):
        """x: a batch of photos, shape (N, 3, 128, 128). Returns 6 raw scores per photo."""
        return self.forward_with_maps(x)[0]

    def forward_with_maps(self, x):
        """Same as forward, but also returns what each convolution layer produced.

        The "feature maps" are each layer's output after ReLU (before pooling):
        one small grayscale picture per filter, bright where that filter found
        its pattern. feature_maps.py draws them.
        """
        maps = []
        for conv in (self.conv1, self.conv2, self.conv3):
            x = self.relu(conv(x))
            maps.append(x)
            x = self.pool(x)
        scores = self.fc(torch.flatten(x, 1))       # (N, 32, 16, 16) -> (N, 8192) -> (N, 6)
        return scores, maps


def count_dead_filters(model, x):
    """For each layer, how many filters never switch on (output 0 everywhere) for the photos x."""
    with torch.no_grad():
        _, maps = model.forward_with_maps(x)
    return [int((m.amax(dim=(0, 2, 3)) == 0).sum()) for m in maps]


def count_parameters(model):
    """How many numbers the network learns (weights and biases)."""
    return sum(p.numel() for p in model.parameters())


def load_trained(path):
    """Load a saved network (from train.py) ready for guessing. Returns (model, checkpoint info)."""
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = FingerCNN()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()                                     # guessing mode (no training behavior)
    return model, ckpt
