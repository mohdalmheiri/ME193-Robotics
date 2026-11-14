"""
The SAME tests Julian does by hand on the real robot, run in the simulator, so real and sim
results can sit side by side (rubric: "simulation and reality somewhat close").

Julian measures (no laptop): weight, axle height, leg rpm at full speed, which spin direction
walks vs flips, and 10-second straight-line runs at full speed with the legs in step and out
of step (distance, sideways offset, turn angle, filmed from above).

How it works: uses FakeRobot's physics (robot/model/scene.xml = the training model) with no
sensor noise and no laptop in the loop: both motors simply run at one fixed speed, like
pressing "go" on the hub.
  1. Weight: total mass of the model (body + both legs).
  2. Axle height: the nominal robot is set down with both legs pointing forward, left to
     settle for 1 s, and the axle's height above the table is measured.
  3. Leg rpm at full speed: what the simulator ASSUMES (--rpm, default 120 = the policy's
     top speed). Julian's number replaces it: rerun with --rpm <his value>.
  4. Spin direction: 5 s at full speed each way; reports which way walks and which flips,
     and describes the walking direction in words he can check by eye.
  5. 10 s straight-line runs at full speed (--rpm), legs in step (both legs at the same
     angle) and out of step (one leg turned --phase-deg further, default 90 = a quarter turn,
     as Julian does it; both legs start pointing straight forward, flat), each on the nominal robot and
     on 20 lopsided robots (randomized as in training: friction, mass, center of mass,
     motor speed +/-10 % and strength per side). Measured like Julian does:
       distance        straight line from start to end point (mm)
       sideways        offset from the start line at the end (mm, + = robot's right)
       turn angle      heading change (deg, + = turned LEFT / counter-clockwise from above)
Outputs: docs/hand_tests_sim.md  (table with an empty "Julian (real)" column to fill in)
         docs/media/hand_tests_sim_paths.png  (paths from above, like his video)
         docs/data/hand_tests_sim.csv  (every robot's numbers)
Spec motor (Julian's published specs, config.MOTOR_SPEC; see robot/fake_robot.py):
  --motor regulated|pwm   the real motor's torque curve (hub holds speed / percent = voltage)
  --percent P             power setting like on the hub; leg speed from config.RPM_AT_PERCENT
                          (placeholder 334 rpm at 100 %), replaces --rpm
  --body-mass-kg 0.080    body mass (motor weight 80 g)
  --tag NAME              write docs/hand_tests_sim_NAME.md (and _NAME .csv/.png) instead of
                          overwriting the default files
Run from the HW8 folder:  ../../.venv/bin/python robot/sim_hand_tests.py [--rpm 120] [--phase-deg 180]
  ../../.venv/bin/python robot/sim_hand_tests.py --motor regulated --percent 35 --body-mass-kg 0.080 --tag spec_35
"""

import argparse
import csv
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
from fake_robot import FakeRobot  # noqa: E402
import units as U  # noqa: E402
MASS = U.META["randomization"]["mass_scale"]      # the exported model's training range

p = argparse.ArgumentParser(description="Simulated versions of Julian's hand tests")
p.add_argument("--rpm", type=float, default=120.0, help="leg speed at full speed (Julian's measurement)")
p.add_argument("--phase-deg", type=float, default=90.0,
               help="leg angle difference for 'out of step' (Julian: one leg turned a quarter turn)")
p.add_argument("--start-deg", type=float, default=0.0,
               help="start angle of the legs (Julian: 0 = both pointing straight forward, flat)")
p.add_argument("--seconds", type=float, default=10.0)
p.add_argument("--lopsided", type=int, default=20)
p.add_argument("--armature", type=float, default=None,
               help="motor inertia override (default: the exported model's; v2 = 2e-4)")
p.add_argument("--motor", choices=["training", "regulated", "pwm"], default="training")
p.add_argument("--percent", type=float, default=None, help="hub power setting (replaces --rpm)")
p.add_argument("--body-mass-kg", type=float, default=None)
p.add_argument("--tag", default="")
a = p.parse_args()
if a.percent is not None:
    a.rpm = U.percent_to_rpm(a.percent)       # the rpm table's speed for this percent
RAD_S = a.rpm * 2 * math.pi / 60
SUFFIX = f"_{a.tag}" if a.tag else ""
FAKE_KW = {"armature": a.armature, "body_mass_kg": a.body_mass_kg,
           "motor": None if a.motor == "training" else a.motor}
SPEED_TXT = (f"{a.percent:.0f} % (= {a.rpm:.0f} rpm no-load from the rpm table)" if a.percent is not None
             else f"{a.rpm:.0f} rpm")


def constant_run(seed, randomize, q_start, seconds, direction=-1):
    """Both motors at one fixed speed, no laptop in the loop. direction -1 = the simulator's
    upright walking direction (negative joint speed), +1 = the other way.
    Returns the result dict and the path [(sideways mm, forward mm, time s, heading deg)].
    A robot that flips (tilt past 70 deg) is stopped there: its distance and turn are the
    values at the moment it flipped (as in evaluate.py), because what a robot on its back
    does afterwards (e.g. spinning around for 7000 deg) says nothing about walking.
    At 100 % power on the spec motor a flipped robot can be thrown into the air, spinning
    faster than the 0.002 s physics step can follow; the simulation then breaks down
    ("unstable"). That only happens after it has tipped, so it also counts as a flip."""
    f = FakeRobot(seed=seed, randomize=randomize, noise=False, start_q=q_start, start_yaw=0.0,
                  **FAKE_KW)
    f.connect()
    f.wanted = direction * RAD_S * np.array([f.motor_scale["right"], f.motor_scale["left"]])
    path, max_tilt, unstable = [(0.0, 0.0, 0.0, 0.0)], 0.0, False
    while f.now() < seconds - 1e-9 and max_tilt <= 70:
        try:
            f.wait_until(f.now() + 0.05)
        except RuntimeError:
            unstable = True
            break
        t = f.truth()
        path.append((t["side_mm"], t["fwd_mm"], f.now(), t["heading_deg"]))
        max_tilt = max(max_tilt, t["tilt_deg"])
    path = np.array(path)
    # keep counting past +/-180 deg, so a robot that turns 1.5 times reads 540, not 180
    path[:, 3] = np.degrees(np.unwrap(np.radians(path[:, 3])))
    side, fwd = path[-1, 0], path[-1, 1]
    return {"distance_mm": math.hypot(side, fwd), "forward_mm": fwd, "sideways_mm": side,
            "turn_deg": float(path[-1, 3]), "max_tilt_deg": max_tilt,
            "flipped": max_tilt > 70 or unstable, "flip_time_s": float(path[-1, 2]),
            "unstable": unstable}, path


# ------------------------------------------------------------------ 1-3 static numbers
f = FakeRobot(seed=0, randomize=False, noise=False, start_q=[0.0, 0.0], start_yaw=0.0, **FAKE_KW)
mass_g = sum(f.m.body_mass[f.m.body(b).id] for b in ("robot/body", "robot/leg_right", "robot/leg_left")) * 1000
f.connect()
f.wait_until(1.0)
axle_mm = f.d.qpos[2] * 1000          # the body frame's origin is on the motor axle
# ------------------------------------------------------------------ 4 spin direction
walk, _ = constant_run(0, False, [math.radians(a.start_deg)] * 2, 5.0, direction=-1)
other, _ = constant_run(0, False, [math.radians(a.start_deg)] * 2, 5.0, direction=+1)
# Describe the walking spin in words: where does the leg tip go when it points DOWN?
# At q = -90 deg the leg points down; with negative joint speed its tip moves...
f2 = FakeRobot(seed=0, randomize=False, noise=False, start_q=[-math.pi / 2, -math.pi / 2], start_yaw=0.0)
import mujoco  # noqa: E402
leg = f2.m.body("robot/leg_right").id
f2.d.qvel[:] = 0
f2.d.qvel[f2.vadr["right"]] = -1.0
mujoco.mj_forward(f2.m, f2.d)
vel = np.zeros(6)
tip_local = np.array([0.048, 0.0, 0.0])          # leg tip, 48 mm along the leg
tip_world = f2.d.xpos[leg] + f2.d.xmat[leg].reshape(3, 3) @ tip_local
mujoco.mj_objectVelocity(f2.m, f2.d, mujoco.mjtObj.mjOBJ_BODY, leg, vel, 0)
w, v0 = vel[:3], vel[3:]
tip_vel = v0 + np.cross(w, tip_world - f2.d.xpos[leg])
tip_z = (tip_world - f2.d.xpos[leg])[2]
bottom_goes = "BACKWARD" if tip_vel[1] < 0 else "FORWARD"
words = (f"walking direction: when a leg points down, its tip sweeps {bottom_goes} along the "
         f"table (like a wheel {'rolling forward' if bottom_goes == 'BACKWARD' else 'rolling backward'}); "
         f"the robot walks toward the end the legs point to at angle 0 (the long arm).")
if tip_z > -0.03:
    words += " (CHECK: leg-down test point was not below the axle)"

# ------------------------------------------------------------------ 5 straight-line runs
tests = {}
for label, phase in (("in step", 0.0), ("out of step", a.phase_deg)):
    q = [math.radians(a.start_deg), math.radians(a.start_deg + phase)]
    nominal, nom_path = constant_run(0, False, q, a.seconds)
    lops = [constant_run(seed, True, q, a.seconds) for seed in range(1, a.lopsided + 1)]
    tests[label] = {"nominal": nominal, "nom_path": nom_path,
                    "lops": [r for r, _ in lops], "lop_paths": [p_ for _, p_ in lops]}

# ------------------------------------------------------------------ outputs
def lop_cell(rs, key):
    """Median (range) over the lopsided robots that stayed UPRIGHT (a flipped robot's distance
    and turn are not a walking result)."""
    x = np.array([r[key] for r in rs if not r["flipped"]])
    if len(x) == 0:
        return "all flipped"
    note = "" if len(x) == len(rs) else f", {len(x)} upright robots"
    return f"{np.median(x):+.0f} (range {x.min():+.0f} to {x.max():+.0f}{note})"


def nom_cell(r, key, fmt):
    return format(r[key], fmt) + (f" (flipped at {r['flip_time_s']:.1f} s)" if r["flipped"] else "")


def flip_cell(rs):
    k = [r for r in rs if r["flipped"]]
    times = f", median at {np.median([r['flip_time_s'] for r in k]):.1f} s" if k else ""
    return f"{len(k)} of {len(rs)}{times}"


lines = ["# Julian's hand tests, simulated", "",
         f"Simulator: `robot/model/scene.xml` (the training model), motor inertia "
         f"{a.armature if a.armature else 'as exported'}, motor: "
         f"{ {'training': 'the training motor (0.10 N m limit)', 'regulated': 'SPEC motor, hub holds speed', 'pwm': 'SPEC motor, percent = voltage'}[a.motor] }"
         f"{f', body {a.body_mass_kg * 1000:.0f} g' if a.body_mass_kg else ''}, setting {SPEED_TXT}, "
         f"{a.seconds:.0f} s runs, legs start at {a.start_deg:.0f} deg (0 = pointing forward); "
         f"'out of step' = legs {a.phase_deg:.0f} deg apart. Lopsided robots: {a.lopsided}, randomized "
         "as in training. Generated by `robot/sim_hand_tests.py`.", "",
         "| Test | Simulator, nominal robot | Simulator, lopsided robots: median (range) | Julian (real) |",
         "|---|---|---|---|",
         f"| Weight (g) | {mass_g:.0f} | body mass x{MASS[0]:g}-{MASS[1]:g} | |",
         f"| Axle height above table, legs forward, at rest (mm) | {axle_mm:.1f} | | |",
         f"| Leg speed at this setting (rpm) | {a.rpm:.0f} (assumed{', no load' if a.motor != 'training' else ''}) | x0.9-1.1 per side | |",
         f"| Spin direction that walks (5 s) | {walk['forward_mm']:.0f} mm forward, max tilt {walk['max_tilt_deg']:.0f} deg"
         f"{' - FLIPPED at %.1f s' % walk['flip_time_s'] if walk['flipped'] else ''} | | |",
         f"| Other spin direction (5 s) | {'FLIPS at %.1f s' % other['flip_time_s'] if other['flipped'] else 'does not flip'} "
         f"(max tilt {other['max_tilt_deg']:.0f} deg), {other['forward_mm']:.0f} mm forward | | |"]
for label, T in tests.items():
    n = T["nominal"]
    lines += [f"| {label}: distance (mm) | {nom_cell(n, 'distance_mm', '.0f')} | {lop_cell(T['lops'], 'distance_mm')} | |",
              f"| {label}: sideways offset (mm, + = right) | {nom_cell(n, 'sideways_mm', '+.0f')} | {lop_cell(T['lops'], 'sideways_mm')} | |",
              f"| {label}: turn angle (deg, + = left) | {nom_cell(n, 'turn_deg', '+.0f')} | {lop_cell(T['lops'], 'turn_deg')} | |",
              f"| {label}: flipped | {'yes, at %.1f s' % n['flip_time_s'] if n['flipped'] else 'no'} | {flip_cell(T['lops'])} | |"]
lines += ["", "A robot that flips is stopped at that moment; its distance/sideways/turn are the values when it "
          "flipped, and lopsided medians use only the robots that stayed upright.", "",
          f"Spin direction in words: {words}"]
(HW8 / "docs" / f"hand_tests_sim{SUFFIX}.md").write_text("\n".join(lines) + "\n")
(HW8 / "docs" / "data").mkdir(exist_ok=True)
with open(HW8 / "docs" / "data" / f"hand_tests_sim{SUFFIX}.csv", "w", newline="") as fh:
    w_ = csv.writer(fh)
    w_.writerow(["test", "robot", "distance_mm", "forward_mm", "sideways_mm", "turn_deg", "max_tilt_deg", "flipped"])
    for label, T in tests.items():
        for name, r in [("nominal", T["nominal"])] + [(f"lopsided_{i + 1}", r) for i, r in enumerate(T["lops"])]:
            w_.writerow([label, name] + [round(r[k], 1) if isinstance(r[k], float) else r[k]
                                         for k in ("distance_mm", "forward_mm", "sideways_mm", "turn_deg", "max_tilt_deg", "flipped")])
# heading over time for every robot, for robot/compare_drift.py
with open(HW8 / "docs" / "data" / f"hand_tests_sim_heading{SUFFIX}.csv", "w", newline="") as fh:
    w_ = csv.writer(fh)
    w_.writerow(["test", "robot", "t", "heading_deg", "sideways_mm", "forward_mm"])
    for label, T in tests.items():
        for name, pth in [("nominal", T["nom_path"])] + [(f"lopsided_{i + 1}", q) for i, q in enumerate(T["lop_paths"])]:
            for side, fwd, t_, h in pth:
                w_.writerow([label, name, round(t_, 3), round(h, 2), round(side, 1), round(fwd, 1)])
fig, axes = plt.subplots(1, 2, figsize=(11, 6), sharex=True, sharey=True)
for ax, (label, T) in zip(axes, tests.items()):
    for pth in T["lop_paths"]:
        ax.plot(pth[:, 0], pth[:, 1], color="tab:blue", lw=0.8, alpha=0.5)
    ax.plot(T["nom_path"][:, 0], T["nom_path"][:, 1], color="black", lw=2, label="nominal robot")
    ax.axvline(0, color="green", lw=1, label="start line")
    ax.set(title=f"Legs {label}, {SPEED_TXT}, {a.seconds:.0f} s", xlabel="sideways (mm, + = right)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
axes[0].set_ylabel("forward (mm)")
fig.suptitle("Simulated hand tests, seen from above (blue = 20 lopsided robots)")
fig.tight_layout()
fig.savefig(HW8 / "docs" / "media" / f"hand_tests_sim_paths{SUFFIX}.png", dpi=110)
print("\n".join(lines))
print(f"\nSaved docs/hand_tests_sim{SUFFIX}.md, docs/data/hand_tests_sim{SUFFIX}.csv, "
      f"docs/data/hand_tests_sim_heading{SUFFIX}.csv, docs/media/hand_tests_sim_paths{SUFFIX}.png")
