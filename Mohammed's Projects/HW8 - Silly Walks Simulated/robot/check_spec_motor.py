"""
Robustness test: does the policy still walk straight, without flipping, on a robot built
from the REAL motor's published specs instead of the simulator's guessed motor?

The specs (Julian, 2026-11-14, config.MOTOR_SPEC; source still to be confirmed):
  motor weight 80 g; no-load speed 322-346 rpm and stall torque 0.148-0.173 N m at 4.2 V.
The simulator's motor: 0.10 N m torque limit, any speed. So the real motor is ~2.5x faster
and ~1.6x stronger at a standstill; but a DC motor's torque falls as it speeds up:
stall x (1 - speed / no-load speed), e.g. ~0.11 N m left at 110 rpm.

How it works: 100 FakeRobots (seeds 0-99, each a random lopsided robot from the training
ranges), 20 s each, driven through the real control loop (run_policy.run: hub units ->
units.py -> policy -> rpm inside the trained range -> percent -> Bluetooth delay -> motor).
Setups (FakeRobot options):
  training motor            the motor the policy trained with (the normal FakeRobot check)
  spec motor, hub holds speed, 80 g     motor="regulated", body_mass_kg=0.080
  spec motor, no speed control, 80 g    motor="pwm",       body_mass_kg=0.080
  ... the regulated spec motor again with config.POLICY_TOP_RPM = 80 / 140 rpm (the edges of
      the trained range), to help choose the setting for the real robot
Each setup runs the policy and a BASELINE (both legs at the policy's own average command in
that setup, constant). Measures (true values from the simulator, at the end or when the run
stopped because the robot tipped past 70 deg): sideways drift, heading error, forward
distance, flips, and the largest body tilt seen during the run (the tipping margin).

Output: docs/spec_motor_check.md and docs/media/spec_motor_paths.png
Run from the HW8 folder:  ../../.venv/bin/python robot/check_spec_motor.py
"""

import importlib
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
SPEC = {"body_mass_kg": C.MOTOR_SPEC["weight_kg"]}
SETUPS = [  # (label, FakeRobot options, POLICY_TOP_RPM)
    ("training motor", {}, 110.0),
    ("spec motor, hub holds speed, 80 g", {"motor": "regulated", **SPEC}, 110.0),
    ("spec motor, no speed control (PWM), 80 g", {"motor": "pwm", **SPEC}, 110.0),
    ("spec motor, hub holds speed, 80 g, top 80 rpm", {"motor": "regulated", **SPEC}, 80.0),
    ("spec motor, hub holds speed, 80 g, top 140 rpm", {"motor": "regulated", **SPEC}, 140.0),
]


def set_top(rpm):
    """Change config.POLICY_TOP_RPM and rebuild units.py's numbers (run_policy uses the same
    units module object, so it sees the change)."""
    C.POLICY_TOP_RPM = rpm
    importlib.reload(U)


def drive(fake_kw, act, label):
    """100 robots with one driver. act: a policy callable (obs -> action)."""
    out = {k: [] for k in ("side", "head", "fwd", "flipped", "tilt_max", "paths", "actions")}
    for seed in range(N):
        fake = FakeRobot(seed=seed, **fake_kw)
        path, tilts = [], []

        def hook(k, r):
            t = r.truth()
            path.append((t["side_mm"], t["fwd_mm"]))
            tilts.append(t["tilt_deg"])

        acts = []
        pol = (lambda obs: acts.append(np.clip(a := act(obs), -1, 1)) or a)
        s = run(fake, SECONDS, None, policy=pol, on_decision=hook, quiet=True)
        t = s["truth"]
        out["side"].append(t["side_mm"]); out["head"].append(t["heading_deg"]); out["fwd"].append(t["fwd_mm"])
        out["flipped"].append(s["reason"].startswith("tipped"))
        out["tilt_max"].append(max(tilts) if tilts else float("nan"))
        out["paths"].append(np.array(path)); out["actions"] += acts
        if s["reason"] != "time limit reached" and not s["reason"].startswith("tipped"):
            print(f"  robot {seed}: unexpected stop: {s['reason']}")
    for k in ("side", "head", "fwd", "flipped", "tilt_max"):
        out[k] = np.array(out[k])
    print(f"  {label:60s} heading |mean| {np.abs(out['head']).mean():5.1f} deg, drift |mean| "
          f"{np.abs(out['side']).mean():5.0f} mm, forward {out['fwd'].mean():6.0f} mm, "
          f"flips {out['flipped'].sum()}/{N}, max tilt median {np.median(out['tilt_max']):.0f} deg",
          flush=True)
    return out


print(f"{N} FakeRobots x {SECONDS:.0f} s, policy {U.META['checkpoint']} ({U.META.get('task', 'v1')})")
results = []
for label, kw, top in SETUPS:
    set_top(top)
    print(f"{label} (POLICY_TOP_RPM {top:.0f}; full action = {U.command(np.ones(2))[0]['right'] * C.UPRIGHT_PERCENT_SIGN['right']} %)")
    P = drive(kw, Policy(), "policy")
    c = float(np.mean(P["actions"]))
    pct = int(round(U.rpm_to_percent(U.MAX_RPM * (c + 1) / 2)))
    B = drive(kw, lambda obs, c=c: np.array([c, c]), f"baseline (constant {pct} %)")
    results.append((label, top, P, B, pct))
set_top(110.0)


# ------------------------------------------------------------------ table
def m(x):
    return f"{np.abs(x).mean():.0f} / {np.median(np.abs(x)):.0f} / {np.percentile(np.abs(x), 95):.0f}"


lines = ["# Robustness test: the real motor's specs in FakeRobot", "",
         f"- Policy: `{U.META['checkpoint']}`. {N} random lopsided FakeRobots (seeds 0-{N - 1}, the same "
         f"robots in every row), {SECONDS:.0f} s each, through `robot/run_policy.py` (generated by "
         "`robot/check_spec_motor.py`).",
         "- Spec motor (Julian, 2026-11-14, source to be confirmed): no-load 322-346 rpm, stall "
         "0.148-0.173 N m at 4.2 V, each side drawn from these ranges; body 80 g (training: "
         "100 g x 0.6-1.6). Training motor: 0.10 N m limit (x0.8-1.2), any speed.",
         "- \"Hub holds speed\": training's speed controller (0.05 N m per rad/s of error), limited "
         "by the DC motor's torque at its current speed. \"No speed control (PWM)\": percent = "
         "voltage, torque = stall x (percent/100 - speed/no-load speed). Which one the LEGO hub "
         "does is unknown until Monday's calibration (measure_rpm.py on the stand vs on the table).",
         "- The policy's action becomes an rpm inside the trained range FIRST (full action = "
         "POLICY_TOP_RPM), then a percent from the rpm table (placeholder: 334 rpm at 100 %).",
         "- Values: mean / median / worst 5 % of the absolute value at the end; forward: mean; "
         "max tilt: median and worst of each robot's largest body tilt (flip = 70 deg).", "",
         "| Setup | Driver | Sideways drift (mm) | Heading error (deg) | Forward (mm) | Flipped | "
         "Max tilt, median / worst (deg) |",
         "|---|---|---|---|---|---|---|"]
for label, top, P, B, pct in results:
    for name, R in ((f"policy (full action = {top:.0f} rpm)", P), (f"baseline, constant {pct} %", B)):
        lines.append(f"| {label} | {name} | {m(R['side'])} | {m(R['head'])} | {R['fwd'].mean():.0f} | "
                     f"{R['flipped'].sum()} of {N} | {np.median(R['tilt_max']):.0f} / "
                     f"{np.nanmax(R['tilt_max']):.0f} |")
(HW8 / "docs" / "spec_motor_check.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines[-2 * len(results) - 2:]))

# ------------------------------------------------------------------ paths plot (first 3 setups)
fig, axes = plt.subplots(2, 3, figsize=(15, 10), sharex=True, sharey=True)
for col, (label, top, P, B, pct) in enumerate(results[:3]):
    for row, (name, R) in enumerate((("policy", P), (f"baseline {pct} %", B))):
        ax = axes[row, col]
        for p, fl in zip(R["paths"], R["flipped"]):
            if len(p):
                ax.plot(p[:, 0], p[:, 1], lw=0.7, color="tab:red" if fl else "tab:blue", alpha=0.7)
        ax.axvline(0, color="green", lw=1)
        ax.set_title(f"{label}\n{name}", fontsize=10)
        ax.grid(alpha=0.3)
        if row == 1:
            ax.set_xlabel("sideways (mm, + = right)")
        if col == 0:
            ax.set_ylabel("forward (mm)")
fig.suptitle(f"{N} FakeRobots, {SECONDS:.0f} s: training motor vs the real motor's specs (red = flipped)")
fig.tight_layout()
fig.savefig(HW8 / "docs" / "media" / "spec_motor_paths.png", dpi=100)
print("Saved docs/spec_motor_check.md and docs/media/spec_motor_paths.png")
