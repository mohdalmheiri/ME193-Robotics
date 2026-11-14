"""
Proof that  FakeRobot's hub readings  ->  units.py  ->  the 16 numbers the policy saw in
training, and that the policy's output -> percent -> the leg speed training would have used.

How it works:
  robot/tests/data/training_reference.npz was recorded by train/export_policy.py in the REAL
  training environment (MJLab, noise switched off): 4 lopsided robots x 200 decisions, with
  the full physical state at each decision and the 16 inputs the policy saw.
  For every recorded decision this test:
    1. puts that exact physical state into FakeRobot's MuJoCo model,
    2. lets the fake hub produce a sensor message in LEGO units (milli-g, deg/s, whole
       degrees, encoder degrees, ...), noise off,
    3. converts it with units.py, and
    4. compares with the recorded training inputs.
  The two sides share no code: training computed its inputs with MJLab's functions from
  the simulator state; this side goes through the hub's units and back.
  Expected differences: the hub reports whole numbers (whole degrees, whole deg/s), so
  angles can differ by up to 0.5 deg (0.009 in sin/cos) and gyro by 0.5 deg/s (0.009 rad/s).
  Leg speed is the one input computed differently ON PURPOSE: from how far the encoder
  turned over the last 0.05 s, not the instantaneous speed training used. That difference
  is measured and compared with the 5 % speed noise the policy was trained with.

  It then repeats the comparison with a deliberately DIFFERENT hub setup in config.py
  (axes swapped, signs flipped, tenths of a degree), to show the sign/axis/unit settings
  are really used consistently, not just all left at their defaults.

  Finally it checks the command path: action -> units.command() -> percent -> the leg speed
  the fake motor runs, against training's  -120 rpm * (a + 1) / 2.

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_units.py
"""

import importlib
import math
import sys
from pathlib import Path

import mujoco
import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))
import config as C  # noqa: E402
import units as U  # noqa: E402
import fake_robot as F  # noqa: E402
from robot_interface import to_robot_sides  # noqa: E402

REF = np.load(ROBOT_DIR / "tests" / "data" / "training_reference.npz")
QUANT = math.radians(0.5) + 1e-6          # whole-degree rounding
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ({detail})" if detail else ""))


def fake_readings_for_reference():
    """Readings (and converted inputs) for every recorded decision, via FakeRobot + units."""
    fake = F.FakeRobot(seed=0, randomize=False, noise=False)
    n_robots, n_steps = REF["qpos"].shape[:2]
    obs = np.zeros((n_robots, n_steps, 16))
    for i in range(n_robots):
        legs = U.LegSpeed()
        last = np.zeros(2)
        for k in range(n_steps):
            fake.d.qpos[:] = REF["qpos"][i, k]
            fake.d.qvel[:] = REF["qvel"][i, k]
            fake.d.time = k * U.META["decision_dt_s"]
            mujoco.mj_forward(fake.m, fake.d)
            fake.yaw_at_connect = float(REF["start_yaw"][i])   # heading measured from the start
            fake.t_connect = 0.0
            fake._take_sensor_message()
            r = to_robot_sides(fake.last)           # what read() returns (robot legs)
            obs[i, k] = U.observation(r, legs.update(r), last)
            last = np.clip(REF["action"][i, k], -1, 1)
    return obs


def compare(obs, label):
    # Each robot's FIRST recorded decision is skipped: it was recorded right after MJLab's
    # reset, before its first physics step, and there MJLab's leg angles differ from the
    # simulator state by ~1 deg (from the 2nd decision on, all 796 others match exactly).
    # A recording quirk on the training side, not a unit error.
    ref = REF["obs"][:, 1:]
    err = np.abs(obs[:, 1:] - ref)
    check(f"{label}: tilt (gravity direction) matches", err[..., 0:3].max() <= 0.012,
          f"max diff {err[..., 0:3].max():.4f}; whole-degree rounding allows ~0.009-0.012")
    check(f"{label}: gyro (rad/s) matches", err[..., 3:6].max() <= QUANT,
          f"max diff {err[..., 3:6].max():.4f} rad/s; rounding allows {QUANT:.4f}")
    check(f"{label}: heading sin/cos matches", err[..., 6:8].max() <= QUANT,
          f"max diff {err[..., 6:8].max():.4f}")
    check(f"{label}: leg angle sin/cos matches", err[..., 8:12].max() <= QUANT,
          f"max diff {err[..., 8:12].max():.4f}")
    check(f"{label}: last command matches", err[..., 14:16].max() < 1e-6,
          f"max diff {err[..., 14:16].max():.2e}")
    if C.LEG_SPEED_SOURCE == "hub_speed":
        # The hub's speed byte holds -127..127 %, i.e. at most 1.27 x full speed; training's
        # spikes beyond that cannot be reported by ANY hub, so they are counted separately.
        ok_range = np.abs(ref[..., 12:14]) <= 1.27
        e = err[..., 12:14][ok_range]
        one_pct = 0.005 + 1e-6                                 # whole-percent rounding (half of 1 %)
        check(f"{label}: leg speed via the hub's speed report matches training", e.max() <= one_pct,
              f"max diff {e.max():.4f} of full speed; rounding allows {one_pct:.4f}; "
              f"{(~ok_range).mean() * 100:.1f} % of training values were beyond what a hub can report")
    else:
        # KNOWN GAP, measured not judged: the encoder gives the AVERAGE speed over the last
        # 0.05 s, training gave the instantaneous (spiky) simulator speed.
        e = err[..., 12:14]
        print(f"  [INFO] {label}: leg speed via encoder average differs from training's "
              f"instantaneous speed: median {np.median(e):.3f}, 90th percentile "
              f"{np.percentile(e, 90):.3f} of full speed (training noise was 5 %). Effect on "
              "walking: see check_fake_vs_eval.py")
    return err


print("1. Default hub setup (config.py as it is now)")
C.LEG_SPEED_SOURCE = "hub_speed"
compare(fake_readings_for_reference(), "default, leg speed from hub")
C.LEG_SPEED_SOURCE = "encoder"
compare(fake_readings_for_reference(), "default, leg speed from encoder")

print("\n2. A deliberately different hub setup (axes swapped, signs flipped, tenths of a degree)")
saved = {k: getattr(C, k) for k in ("BODY_FROM_HUB", "ANGLE_UNIT_DEG", "PITCH_SIGN", "ROLL_SIGN",
                                    "YAW_SIGN", "GYRO_SIGN", "ENCODER_SIGN", "LEG_ZERO_DEG")}
C.BODY_FROM_HUB = {"x": "-y", "y": "+x", "z": "+z"}
C.ANGLE_UNIT_DEG, C.PITCH_SIGN, C.ROLL_SIGN, C.YAW_SIGN, C.GYRO_SIGN = 0.1, -1, -1, -1, -1
C.ENCODER_SIGN = {"right": +1, "left": -1}
C.LEG_ZERO_DEG = {"right": 123.0, "left": 300.0}
C.LEG_SPEED_SOURCE = "hub_speed"
C.UPRIGHT_PERCENT_SIGN = {"right": -1, "left": +1}
importlib.reload(U)                       # units.py rebuilds its axis matrix from config
compare(fake_readings_for_reference(), "different setup")
C.LEG_SPEED_SOURCE, C.UPRIGHT_PERCENT_SIGN = "encoder", {"right": +1, "left": +1}
for k, v in saved.items():
    setattr(C, k, v)
importlib.reload(U)

print("\n3. Command path: action -> percent -> fake motor leg speed, vs training")
fake = F.FakeRobot(seed=0, randomize=False, noise=False)
worst = 0.0
for a in np.linspace(-1.2, 1.2, 49):             # includes values outside -1..1 (clipped)
    pct, info = U.command(np.array([a, -a]))
    for i, s in enumerate(("right", "left")):
        ai = np.clip([a, -a][i], -1, 1)
        training_speed = -U.MAX_RAD_S * (ai + 1) / 2              # MJLab action term
        fake_speed = fake._pct_to_joint_speed(s, pct[s])
        worst = max(worst, abs(fake_speed - training_speed))
one_pct = U.MAX_RAD_S / 100
check("leg speed from percent matches training's speed for the same action", worst <= one_pct / 2 + 1e-9,
      f"worst {worst * 60 / (2 * math.pi):.2f} rpm; whole-percent rounding allows "
      f"{U.MAX_RPM / 200:.2f} rpm")
_, info = U.command(np.array([1.0, 1.0]))
check("full action (+1) is exactly 100 %, not clipped, with the placeholder table",
      U.command(np.array([1.0, 1.0]))[0]["right"] == 100 * C.UPRIGHT_PERCENT_SIGN["right"] and not info["clipped"])

print("\n4. Speed-limit warning (addition a): a motor slower than 120 rpm must be reported")
saved_table = C.RPM_AT_PERCENT
C.RPM_AT_PERCENT = [(0, 0.0), (50, 50.0), (100, 100.0)]       # pretend: only 100 rpm at 100 %
importlib.reload(U)
pct, info = U.command(np.array([1.0, 0.0]))
check("warning text appears when 100 % gives less than 120 rpm", U.speed_limit_warning() is not None)
check("a full-speed action is clipped to 100 % and reported", pct["right"] == 100 * C.UPRIGHT_PERCENT_SIGN["right"]
      and "right" in info["clipped"], f"wanted {info['clipped'].get('right', 0):.0f} %")
C.RPM_AT_PERCENT = saved_table
importlib.reload(U)
check("no warning with the 120 rpm placeholder table", U.speed_limit_warning() is None)

print("\n5. Physical sanity: a level robot at rest")
fake = F.FakeRobot(seed=0, randomize=False, noise=False, start_q=[0.0, 0.0], start_yaw=0.3)
fake.connect()
fake.wait_until(1.0)                      # let it settle on the table, motors off
r = fake.read()
check("accelerometer reads about +1000 milli-g on z (like MT1's hub lying flat)",
      abs(r.accel_mg[2] - 1000) < 30 and abs(r.accel_mg[0]) < 30 and abs(r.accel_mg[1]) < 30,
      f"{r.accel_mg}")
tilt = U.tilt(r)
check("units.tilt gives gravity pointing down, about (0, 0, -1)", tilt[2] < -0.99, f"{np.round(tilt, 3)}")
check("heading reads 0 after connect (yaw reset)", r.yaw == 0, f"yaw {r.yaw}")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
