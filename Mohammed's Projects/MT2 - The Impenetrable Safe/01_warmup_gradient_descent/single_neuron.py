"""
single_neuron.py - fit ONE neuron to the V data by gradient descent, by hand.

The neuron:   y_hat = ReLU(m * x' + b)
    m is the slope (how steep), b is the offset (where it starts),
    and ReLU(z) = max(0, z): it passes positive numbers through and turns
    negative numbers into 0.

"By hand" means there is no PyTorch here. Every derivative is written out
as a formula, so you can follow (and check in Excel) exactly how m and b
get nudged each step. gradient_descent_5_iterations.xlsx does the same first
5 steps with spreadsheet formulas, and should give the same numbers.

Run:  python single_neuron.py
Out:  a table of iterations 0-5, then single_neuron_fit.png and
      single_neuron_loss.png in this folder.
"""
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")            # draw straight to files, no window needed
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent     # this folder, so the script runs from anywhere
DATA_FILE = HERE / "annacode-v.tsv"

# ---- Rescaling ---------------------------------------------------------------
# The raw data has x from about 20 to 100 and y from about 0 to 80. Gradient
# descent works much better on small numbers centered near 0:
#   * x' = (x - 60) / 40 moves the middle of the data (x = 60) to 0 and squeezes
#     the range 20..100 into -1..+1. If x stayed around 60, the m-step
#     (which is multiplied by x) would be ~60 times bigger than the b-step,
#     so one learning rate could never suit both: too big for m or too small for b.
#   * y' = y / 100 shrinks the outputs to 0..0.8, so the errors, the loss and the
#     gradients are all small numbers and a learning rate near 0.5 is safe.
# The fit is done on x', y'; for plots we turn it back into the original units.
X_CENTER, X_SCALE, Y_SCALE = 60.0, 40.0, 100.0

# ---- Settings ----------------------------------------------------------------
M_START, B_START = 1.0, 0.0   # Anna's Code's default for a new neuron: weight 1, bias 0
# Learning rate 0.5: tried 0.05, 0.2, 0.5, 1, 2 and 4 on this data.
#   0.05 and 0.2 work but crawl (after 5 steps the loss has barely moved).
#   0.5 drops the loss every single step (no overshooting) and m and b move
#       visibly in 5 steps. It is half of 1.0, the largest rate that was still smooth.
#   2 and 4 overshoot: the step jumps past the bottom and the loss goes UP.
LEARNING_RATE = 0.5
TABLE_ITERATIONS = 5          # print the table for iterations 0..5
EPOCHS = 200                  # then keep going this long for the final fit


def load_data():
    """Read the V data and return the rescaled x', y' plus the original x, y."""
    data = np.loadtxt(DATA_FILE, skiprows=1)   # columns: Time (s), x, output 1; skip the header row
    x, y = data[:, 1], data[:, 2]              # time is only a label, so it is not used
    x_s = (x - X_CENTER) / X_SCALE             # x'
    y_s = y / Y_SCALE                          # y'
    return x, y, x_s, y_s


def neuron(m, b, x_s):
    """The neuron itself: ReLU(m*x' + b). Works on one number or a whole array."""
    return np.maximum(0.0, m * x_s + b)


def loss_and_gradients(m, b, x_s, y_s):
    """Mean squared error, and how much it changes when m or b is nudged.

    The formulas, written for all N points at once (numpy does each point):
        z_i      = m*x'_i + b               what goes into the ReLU
        y_hat_i  = ReLU(z_i)                the neuron's guess
        error_i  = y_hat_i - y'_i           how far off the guess is
        active_i = 1 if z_i > 0 else 0      ReLU's slope: 1 where it passes z through, 0 where it outputs 0
        loss     = (1/N) * sum(error_i^2)
        dL/dm    = (2/N) * sum(error_i * active_i * x'_i)
        dL/db    = (2/N) * sum(error_i * active_i)
    Where does the 2 come from? The derivative of error^2 is 2*error.
    Where does active come from? The chain rule: a change in z only reaches
    y_hat if the ReLU is passing z through (slope 1); if it is outputting 0
    (slope 0), nudging m or b changes nothing for that point.
    """
    n = len(x_s)
    z = m * x_s + b
    y_hat = np.maximum(0.0, z)
    error = y_hat - y_s
    active = (z > 0).astype(float)
    loss = np.mean(error ** 2)
    dl_dm = (2.0 / n) * np.sum(error * active * x_s)
    dl_db = (2.0 / n) * np.sum(error * active)
    return loss, dl_dm, dl_db


def train_single_neuron(x_s, y_s, epochs=EPOCHS, lr=LEARNING_RATE,
                        m=M_START, b=B_START, table_rows=0):
    """Plain gradient descent: measure the slope of the loss, step downhill, repeat.

    Each pass ("epoch" or "iteration") uses all the points once. Returns the
    final m, b and the loss at the start of every epoch (plus the final one).
    If table_rows > 0, prints the first iterations as a table.
    """
    if table_rows:
        print(f"Learning rate {lr}, start m = {m}, b = {b}, N = {len(x_s)} points")
        print(f"{'iter':>4} {'m':>10} {'b':>10} {'loss':>10} {'dL/dm':>10} {'dL/db':>10}")
    losses = []
    for it in range(epochs + 1):
        loss, dl_dm, dl_db = loss_and_gradients(m, b, x_s, y_s)
        losses.append(loss)
        if it <= table_rows and table_rows:
            # row "it" shows m and b BEFORE this iteration's step, the loss they give,
            # and the gradients that the step is about to use
            print(f"{it:>4} {m:>10.6f} {b:>10.6f} {loss:>10.6f} {dl_dm:>10.6f} {dl_db:>10.6f}")
        if it == epochs:
            break                      # last pass only measures, no more steps
        # the update: step against the slope, scaled by the learning rate
        m = m - lr * dl_dm
        b = b - lr * dl_db
    return m, b, losses


def main():
    x, y, x_s, y_s = load_data()

    # 1. The first iterations as a table (compare with the Excel Summary sheet)
    print("=== First iterations ===")
    train_single_neuron(x_s, y_s, epochs=TABLE_ITERATIONS, table_rows=TABLE_ITERATIONS)

    # 2. The full training run
    m, b, losses = train_single_neuron(x_s, y_s, epochs=EPOCHS)
    print(f"\n=== After {EPOCHS} epochs ===")
    print(f"m = {m:.4f}, b = {b:.4f}, loss = {losses[-1]:.5f} (started at {losses[0]:.5f})")
    # Back in original units: y = 100*ReLU(m*(x-60)/40 + b) = ReLU(slope*x + intercept) with
    slope = Y_SCALE * m / X_SCALE
    intercept = Y_SCALE * (b - m * X_CENTER / X_SCALE)
    print(f"In original units: y = ReLU({slope:.3f}*x {intercept:+.2f})")
    left = x_s < 0
    print(f"Neuron switched on (active) for {np.sum(m * x_s + b > 0)} of {len(x_s)} points; "
          f"loss from the left half alone: {np.sum((neuron(m, b, x_s[left]) - y_s[left]) ** 2) / len(x_s):.5f}, "
          f"right half alone: {np.sum((neuron(m, b, x_s[~left]) - y_s[~left]) ** 2) / len(x_s):.5f}")

    # 3. Plot: the data and the fitted neuron, in the original units
    x_line = np.linspace(x.min(), x.max(), 400)
    y_line = Y_SCALE * neuron(m, b, (x_line - X_CENTER) / X_SCALE)   # rescale in, compute, rescale out
    plt.figure(figsize=(6.5, 4.2))
    plt.scatter(x, y, s=14, color="#1f6feb", label="V data (120 points)")
    plt.plot(x_line, y_line, color="#d1242f", lw=2.2, label=f"one neuron after {EPOCHS} epochs")
    plt.xlabel("x (input)")
    plt.ylabel("output")
    plt.title("One ReLU neuron fitted to the V")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(HERE / "single_neuron_fit.png", dpi=150)
    plt.close()

    # 4. Plot: loss vs epoch (how fast the fit improved)
    plt.figure(figsize=(6.5, 4.2))
    plt.plot(range(len(losses)), losses, color="#1f6feb", lw=2)
    plt.xlabel("epoch")
    plt.ylabel("loss (mean squared error, rescaled units)")
    plt.title(f"Single neuron: loss vs epoch (learning rate {LEARNING_RATE})")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(HERE / "single_neuron_loss.png", dpi=150)
    plt.close()
    print("Saved single_neuron_fit.png and single_neuron_loss.png")


# Only run when started directly, so two_neurons.py can import the functions above
if __name__ == "__main__":
    main()
