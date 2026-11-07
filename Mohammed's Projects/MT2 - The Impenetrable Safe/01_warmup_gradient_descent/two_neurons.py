"""
two_neurons.py - fit the V with a hidden layer of 2 ReLU neurons, in PyTorch,
and compare it with the single neuron from single_neuron.py.

The network:
    h1 = ReLU(w1 * x' + c1)          hidden neuron 1
    h2 = ReLU(w2 * x' + c2)          hidden neuron 2
    y_hat = v1*h1 + v2*h2 + d        output neuron: a plain weighted sum, no ReLU

Why this can make a V: each hidden neuron is a "hockey stick" (flat, then a
ramp). If one ramp points left and the other points right, adding them gives
two ramps meeting at a corner: a V. One neuron alone only has one ramp.

The training recipe is the same as single_neuron.py (full-batch gradient
descent on mean squared error, same rescaling). The difference is that PyTorch
works out the gradients for us (autograd), because with 7 numbers to tune
writing every derivative by hand gets long.

Run:  python two_neurons.py
Out:  a line per random start, the best network's numbers, and
      two_neurons_vs_one.png in this folder.
"""
import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")            # draw straight to files, no window needed
import matplotlib.pyplot as plt

# Reuse the data loading, rescaling and single-neuron training from single_neuron.py,
# so both fits use exactly the same data and the same numbers.
from single_neuron import (HERE, X_CENTER, X_SCALE, Y_SCALE, load_data,
                           neuron, train_single_neuron)

LEARNING_RATE = 0.1   # plain gradient descent. 0.5 (the single neuron's rate) knocked
                      # more random starts into a stuck state, so a smaller step is used.
EPOCHS = 5000         # 7 numbers to tune and smaller steps, so it needs more passes than 200
SEEDS = range(10)     # how many different random starting points to try


def make_network():
    """1 input -> 2 hidden ReLU neurons -> 1 plain output. PyTorch picks random starting weights."""
    return torch.nn.Sequential(
        torch.nn.Linear(1, 2),   # the two hidden neurons: w1, c1 and w2, c2
        torch.nn.ReLU(),         # the hockey-stick bend
        torch.nn.Linear(2, 1),   # output: v1*h1 + v2*h2 + d (no activation, so it can go up or down freely)
    )


def train(seed, X, Y):
    """Train one network from the random start chosen by `seed`. Returns it and its final loss."""
    torch.manual_seed(seed)                     # same seed -> same random start every run
    net = make_network()
    optimizer = torch.optim.SGD(net.parameters(), lr=LEARNING_RATE)   # SGD on all points = plain gradient descent
    for _ in range(EPOCHS):
        loss = torch.mean((net(X) - Y) ** 2)    # mean squared error, same as the single neuron
        optimizer.zero_grad()                   # clear the last step's gradients
        loss.backward()                         # autograd: dL/d(every weight), via the chain rule
        optimizer.step()                        # weight = weight - learning rate * gradient
    with torch.no_grad():
        final = torch.mean((net(X) - Y) ** 2).item()
    return net, final


def describe(net, X):
    """Say which side of the V each hidden neuron switched on for (left = x' < 0, right = x' > 0)."""
    with torch.no_grad():
        h = torch.relu(net[0](X))               # hidden-neuron outputs for every point
    parts = []
    for j in range(2):
        on = h[:, j] > 0
        left, right = int((on & (X[:, 0] < 0)).sum()), int((on & (X[:, 0] >= 0)).sum())
        parts.append("never on" if left + right == 0 else f"on for {left} left / {right} right")
    return "; ".join(f"neuron {j + 1} {p}" for j, p in enumerate(parts))


def main():
    x, y, x_s, y_s = load_data()
    # PyTorch wants a column of numbers (N rows, 1 column), as 32-bit floats
    X = torch.tensor(x_s, dtype=torch.float32).reshape(-1, 1)
    Y = torch.tensor(y_s, dtype=torch.float32).reshape(-1, 1)

    # 1. Try several random starts. Two-neuron ReLU networks can get stuck,
    #    so this shows how often that happens and keeps the best result.
    print(f"Two hidden ReLU neurons, gradient descent, learning rate {LEARNING_RATE}, {EPOCHS} epochs")
    results = []
    for seed in SEEDS:
        net, final = train(seed, X, Y)
        results.append((final, seed, net))
        print(f"  seed {seed}: loss {final:.5f}  ({describe(net, X)})")
    final, seed, best = min(results, key=lambda r: r[0])
    good = sum(1 for r in results if r[0] < 0.001)
    print(f"{good} of {len(results)} starts found the V (loss < 0.001). Best: seed {seed}, loss {final:.5f}")
    for name, p in best.named_parameters():
        print(f"  {name}: {p.data.numpy().ravel().round(3)}")

    # 2. The single neuron, trained exactly as in single_neuron.py, for comparison
    m, b, losses = train_single_neuron(x_s, y_s)
    print(f"Single neuron for comparison: loss {losses[-1]:.5f}")

    # 3. Plot both fits on the data, in the original units
    x_line = np.linspace(x.min(), x.max(), 400)
    xs_line = (x_line - X_CENTER) / X_SCALE                       # rescale in
    with torch.no_grad():
        y_two = best(torch.tensor(xs_line, dtype=torch.float32).reshape(-1, 1)).numpy().ravel()
    plt.figure(figsize=(6.8, 4.4))
    plt.scatter(x, y, s=14, color="#8c959f", label="V data (120 points)")
    plt.plot(x_line, Y_SCALE * neuron(m, b, xs_line), color="#d1242f", lw=2.2,
             label=f"1 neuron (loss {losses[-1]:.4f})")
    plt.plot(x_line, Y_SCALE * y_two, color="#1f6feb", lw=2.2, ls="--",
             label=f"2 hidden neurons (loss {final:.4f})")              # rescale out (x100)
    plt.xlabel("x (input)")
    plt.ylabel("output")
    plt.title("One neuron vs. a hidden layer of two")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(HERE / "two_neurons_vs_one.png", dpi=150)
    plt.close()
    print("Saved two_neurons_vs_one.png")


if __name__ == "__main__":
    main()
