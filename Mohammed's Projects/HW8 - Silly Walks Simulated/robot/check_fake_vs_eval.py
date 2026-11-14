"""
Does FakeRobot + the real control loop reproduce the evaluation table?

How it works: drives 100 random lopsided FakeRobots (seeds 0-99, 20 s each, as fast as the
computer can) through the SAME code the real robot will use (run_policy.run: hub units ->
units.py -> policy -> percent -> Bluetooth delay -> motors), then measures what evaluate.py
measured: sideways drift, heading error, forward distance, flips (true values, at the end
or at the moment the loop stopped because the robot tipped past 70 deg).
Drivers, all on the same 100 robots:
  baseline            both legs at one constant speed: the policy's average command
                      (as in evaluate.py)
  policy, encoder     the trained policy, leg speed from the encoder average (what the
                      real robot can certainly provide; config default)
  policy, hub speed   the trained policy, leg speed from the hub's speed report, which in
                      FakeRobot is the simulator's instantaneous speed (= what training saw)
The two policy rows show what the leg-speed gap (smooth encoder average vs training's
spiky instantaneous speed) costs.

Output: docs/fake_robot_check.md (table next to evaluate.py's numbers) and
        docs/media/fake_robot_paths.png (every robot's path, from above)
Run from the HW8 folder:  ../../.venv/bin/python robot/check_fake_vs_eval.py
"""

import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent
HW8 = ROBOT_DIR.parent
sys.path.insert(0, str(ROBOT_DIR))
import config as C  # noqa: E402
import units as U  # noqa: E402
from fake_robot import FakeRobot  # noqa: E402
from policy import Policy  # noqa: E402
from run_policy import run  # noqa: E402

N, SECONDS = 100, 20.0
# evaluate.py's results for THIS policy (v1: docs/eval_results_dt0.002.md, v2:
# docs/eval_results_v2_dt0.002.md), read from its table: mean / median / worst 5 %
EVAL_MD = HW8 / "docs" / ("eval_results_v2_dt0.002.md" if U.V2 else "eval_results_dt0.002.md")


def read_eval(path):
    rows = [ln.split("|")[1:-1] for ln in path.read_text().splitlines() if ln.startswith("| ")]
    head = [c.strip() for c in rows[0]]
    col = {"baseline": next(i for i, h in enumerate(head) if h.startswith("Baseline")),
           "policy": head.index("Trained policy")}
    out = {k: {} for k in col}
    keys = {"Sideways drift": "side", "Heading error": "head", "Forward distance": "fwd", "Flipped": "flips"}
    for r in rows[1:]:
        name = next((v for k, v in keys.items() if r[0].strip().startswith(k)), None)
        if name is None:
            continue
        for d, i in col.items():
            nums = [float(x) for x in __import__("re").findall(r"-?\d+(?:\.\d+)?", r[i])]
            out[d][name] = int(nums[0]) if name == "flips" else tuple(nums[:3])
    return out


EVAL = read_eval(EVAL_MD)


class Recorder:
    """Wraps a policy: remembers every action (for the baseline speed) and the path."""
    def __init__(self, inner):
        self.inner, self.actions = inner, []

    def __call__(self, obs):
        a = self.inner(obs)
        self.actions.append(np.clip(a, -1, 1))
        return a


def drive(make_policy, label):
    out = {"side": [], "head": [], "fwd": [], "flipped": [], "paths": [], "actions": [], "clipped": 0}
    for seed in range(N):
        fake = FakeRobot(seed=seed)
        pol = Recorder(make_policy())
        path = []
        hook = lambda k, r: path.append((r.truth()["side_mm"], r.truth()["fwd_mm"]))
        s = run(fake, SECONDS, None, policy=pol, on_decision=hook, quiet=True)
        t = s["truth"]
        out["side"].append(t["side_mm"]); out["head"].append(t["heading_deg"]); out["fwd"].append(t["fwd_mm"])
        out["flipped"].append(s["reason"].startswith("tipped"))
        out["paths"].append(np.array(path)); out["actions"] += pol.actions
        out["clipped"] += s["clipped_decisions"]
        if s["reason"] not in ("time limit reached",) and not s["reason"].startswith("tipped"):
            print(f"  robot {seed}: unexpected stop: {s['reason']}")
    out = {k: (np.array(v) if k in ("side", "head", "fwd", "flipped") else v) for k, v in out.items()}
    print(f"{label:20s} heading median {np.median(np.abs(out['head'])):5.1f} deg, drift median "
          f"{np.median(np.abs(out['side'])):5.0f} mm, forward mean {out['fwd'].mean():6.0f} mm, "
          f"flips {out['flipped'].sum()}/{N}", flush=True)
    return out


def stats(x):
    a = np.abs(x)
    return a.mean(), np.median(a), np.percentile(a, 95)


def fwd_stats(x):
    return x.mean(), np.median(x), np.percentile(x, 5)


print(f"{N} fake robots x {SECONDS:.0f} s each, physics step {U.META['physics_timestep_s']} s, "
      f"policy round {U.META['training_round']}")
C.LEG_SPEED_SOURCE = "encoder"
P_enc = drive(Policy, "policy, encoder")
C.LEG_SPEED_SOURCE = "hub_speed"
P_hub = drive(Policy, "policy, hub speed")     # v2: NOT the source v2 trained on
C.LEG_SPEED_SOURCE = "encoder"
c = float(np.mean(P_enc["actions"]))
rpm = U.MAX_RPM * (c + 1) / 2
print(f"policy's average command {c:+.2f} -> baseline runs both legs at {rpm:.0f} rpm")
B = drive(lambda: (lambda obs: np.array([c, c])), "baseline")

# ------------------------------------------------------------------ table
def cell(t):
    return f"{t[0]:.0f} / {t[1]:.0f} / {t[2]:.0f}"


rows = [("Sideways drift (mm)", "side", stats), ("Heading error (deg)", "head", stats),
        ("Forward distance (mm)", "fwd", fwd_stats)]
lines = ["# FakeRobot check: does the robot-side code reproduce the evaluation?", "",
         f"- {N} random lopsided FakeRobots (seeds 0-{N - 1}), {SECONDS:.0f} s each, driven through "
         "`robot/run_policy.py` (hub units, `units.py`, Bluetooth delay, whole percents).",
         f"- Policy: `{U.META['checkpoint']}`. Physics: `robot/model/scene.xml` (the training model, "
         "elliptic friction, checked field by field against MJLab).",
         f"- Baseline: both legs at a constant {rpm:.0f} rpm (the policy's average command).",
         f"- evaluate.py columns: from `docs/{EVAL_MD.name}` (MJLab, 100 robots, seed 7). "
         "The robots are drawn from the same ranges but are not the same 100, so expect "
         "similar statistics, not identical numbers."
         + (f" v2: evaluate.py draws each robot's top speed from 80-140 rpm; here the robot side "
            f"fixes it at config.POLICY_TOP_RPM = {U.MAX_RPM:.0f} rpm." if U.V2 else ""),
         "- Leg speed input: v2 trained on the encoder average (the 'encoder' column is the real "
         "set-up); the 'hub speed' column is the instantaneous speed, which v2 never saw." if U.V2 else
         "- Leg speed input: v1 trained on the instantaneous speed ('hub speed' column).",
         "- Values: mean / median / worst 5 % of the absolute value (forward: mean / median / "
         "lowest 5 %).", "",
         "| Measure | Baseline: evaluate.py | Baseline: FakeRobot | Policy: evaluate.py | "
         "Policy: FakeRobot, encoder speed | Policy: FakeRobot, hub speed |",
         "|---|---|---|---|---|---|"]
for name, k, f in rows:
    lines.append(f"| {name} | {cell(EVAL['baseline'][k])} | {cell(f(B[k]))} | {cell(EVAL['policy'][k])} | "
                 f"{cell(f(P_enc[k]))} | {cell(f(P_hub[k]))} |")
lines.append(f"| Flipped | {EVAL['baseline']['flips']} of 100 | {B['flipped'].sum()} of {N} | "
             f"{EVAL['policy']['flips']} of 100 | {P_enc['flipped'].sum()} of {N} | {P_hub['flipped'].sum()} of {N} |")
lines.append(f"| Decisions with a command clipped at 100 % | - | {B['clipped']} | - | {P_enc['clipped']} | {P_hub['clipped']} |")
(HW8 / "docs" / "fake_robot_check.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines[-7:]))

# ------------------------------------------------------------------ paths plot
fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), sharex=True, sharey=True)
for ax, (R, title) in zip(axes, [(B, "Baseline (equal speeds)"), (P_enc, "Policy, encoder leg speed"),
                                 (P_hub, "Policy, hub leg speed")]):
    for p, fl in zip(R["paths"], R["flipped"]):
        if len(p):
            ax.plot(p[:, 0], p[:, 1], lw=0.7, color="tab:red" if fl else "tab:blue", alpha=0.7)
    ax.axvline(0, color="green", lw=1)
    ax.set(title=title, xlabel="sideways from start line (mm, + = right)")
    ax.grid(alpha=0.3)
axes[0].set_ylabel("forward along start direction (mm)")
fig.suptitle(f"{N} FakeRobots through the robot-side control loop, {SECONDS:.0f} s (red = flipped)")
fig.tight_layout()
fig.savefig(HW8 / "docs" / "media" / "fake_robot_paths.png", dpi=110)
print("Saved docs/fake_robot_check.md and docs/media/fake_robot_paths.png")
