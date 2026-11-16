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
  the fake motor runs, against training's  -top speed * (a + 1) / 2  (v2: top speed =
  config.POLICY_TOP_RPM, inside the trained 80-140 rpm), and that the real legs can NEVER be
  asked to go faster than training's fastest top speed, even on the ~330 rpm spec motor
  (unit check over all actions, an end-to-end check with a spec-motor FakeRobot on a stand,
  and units.py refusing a POLICY_TOP_RPM outside the trained range).

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
    e = err[..., 12:14]
    if U.V2 and C.LEG_SPEED_SOURCE == "encoder":
        # v2 TRAINED on the encoder average (leg angle change over one decision / 0.05 s), so
        # this must match up to the encoder's whole degrees: two rounded readings differ from
        # the true change by up to 1 deg -> 1 deg / 0.05 s / the input's 120 rpm scale.
        one_deg = math.radians(1.0) / U.META["decision_dt_s"] / U.LEG_SPEED_NORM_RAD_S + 1e-6
        check(f"{label}: leg speed (encoder average) matches training's v2 input", e.max() <= one_deg,
              f"max diff {e.max():.4f}; whole-degree encoder steps allow {one_deg:.4f}")
    elif not U.V2 and C.LEG_SPEED_SOURCE == "hub_speed":
        # v1 trained on the instantaneous speed. The hub's speed byte holds -127..127 %, i.e.
        # at most 1.27 x full speed; training's spikes beyond that cannot be reported by ANY
        # hub, so they are counted separately.
        ok_range = np.abs(ref[..., 12:14]) <= 1.27
        e = e[ok_range]
        one_pct = 0.005 + 1e-6                                 # whole-percent rounding (half of 1 %)
        check(f"{label}: leg speed via the hub's speed report matches training", e.max() <= one_pct,
              f"max diff {e.max():.4f} of full speed; rounding allows {one_pct:.4f}; "
              f"{(~ok_range).mean() * 100:.1f} % of training values were beyond what a hub can report")
    else:
        # KNOWN GAP, measured not judged: this leg-speed source is not what this policy trained on
        print(f"  [INFO] {label}: leg speed from '{C.LEG_SPEED_SOURCE}' is not the source this "
              f"policy trained on; differs by median {np.median(e):.3f}, 90th percentile "
              f"{np.percentile(e, 90):.3f} of the input scale. Effect on walking: see "
              "check_fake_vs_eval.py")
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
C.LEG_SPEED_SOURCE = "encoder" if U.V2 else "hub_speed"     # the source this policy trained on
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
half_pct = U.RPM_AT_100 / 200 * 2 * math.pi / 60           # half of 1 %, in rad/s
check("leg speed from percent matches training's speed for the same action", worst <= half_pct + 1e-9,
      f"worst {worst * 60 / (2 * math.pi):.2f} rpm; whole-percent rounding allows "
      f"{U.RPM_AT_100 / 200:.2f} rpm (1 % = {U.RPM_AT_100 / 100:.2f} rpm with this table)")

print("\n3b. The real legs never go faster than in training (v2: action = fraction of top speed)")
print(f"    policy {U.META.get('task', 'v1')}, trained top speeds {U.TRAINED_TOP_RPM[0]:.0f}-"
      f"{U.TRAINED_TOP_RPM[1]:.0f} rpm, POLICY_TOP_RPM {U.MAX_RPM:.0f}, rpm table top {U.RPM_AT_100:.0f} rpm")
fastest = 0.0
for a in np.linspace(-1.5, 1.5, 301):
    pct, info = U.command(np.array([a, a]))
    for s_ in ("right", "left"):
        fastest = max(fastest, U.percent_to_rpm(abs(pct[s_])))
check("no action asks the motor for more than POLICY_TOP_RPM (+ whole-percent rounding)",
      fastest <= U.MAX_RPM + U.RPM_AT_100 / 200 + 1e-9, f"fastest {fastest:.1f} rpm")
check("... and so never more than the trained range's top", fastest <= U.TRAINED_TOP_RPM[1],
      f"{fastest:.1f} <= {U.TRAINED_TOP_RPM[1]:.0f} rpm")
pct_full = U.command(np.array([1.0, 1.0]))[0]["right"] * C.UPRIGHT_PERCENT_SIGN["right"]
expect = round(100 * U.MAX_RPM / U.RPM_AT_100)
check("full action (+1) gives POLICY_TOP_RPM's percent, not 100 %", pct_full == expect,
      f"{pct_full} % (= {U.MAX_RPM:.0f} of {U.RPM_AT_100:.0f} rpm); "
      f"the naive 100 x (a + 1) / 2 would send 100 % = {U.RPM_AT_100:.0f} rpm")
# end to end, on a stand (legs free = the fastest they can go), full action:
#  - the motor from the PUBLISHED specs (~334 rpm, config.MOTOR_SPEC) described by its own table
#    (the 334 rpm placeholder). It has to be its own table: the real robot's measured table
#    (165.8 rpm at 100 %, 2026-11-16) describes a different, slower motor, and pairing the two
#    makes a fake hub that contradicts itself.
#  - the CALIBRATED robot: config.py's measured table with FakeRobot's normal motor
SPEC_TABLE = [(0, 0.0), (25, 83.5), (50, 167.0), (75, 250.5), (100, 334.0)]
calibrated_table = C.RPM_AT_PERCENT
C.RPM_AT_PERCENT = SPEC_TABLE
importlib.reload(U)
for mode in ("regulated", "pwm"):
    fake = F.FakeRobot(seed=0, randomize=False, noise=False, start_q=[0.0, 0.0], motor=mode)
    fake.connect()
    fake.on_stand()
    pct, _ = U.command(np.array([1.0, 1.0]))
    fake.send(pct["right"], pct["left"])
    fake.wait_until(1.0)                                    # spin up
    q0 = {s_: fake.d.qpos[fake.qadr[s_]] for s_ in ("right", "left")}
    fake.wait_until(3.0)
    rpm = max(abs(fake.d.qpos[fake.qadr[s_]] - q0[s_]) / 2.0 * 60 / (2 * math.pi) for s_ in ("right", "left"))
    fake.close()
    check(f"spec motor ({mode}), legs free, full action: legs run at about POLICY_TOP_RPM, not ~330 rpm",
          abs(rpm - U.MAX_RPM) <= 0.05 * U.MAX_RPM and rpm <= U.TRAINED_TOP_RPM[1], f"{rpm:.1f} rpm")
C.RPM_AT_PERCENT = calibrated_table
importlib.reload(U)
fake = F.FakeRobot(seed=0, randomize=False, noise=False, start_q=[0.0, 0.0])
fake.connect()
fake.on_stand()
pct, _ = U.command(np.array([1.0, 1.0]))
fake.send(pct["right"], pct["left"])
fake.wait_until(1.0)
q0 = {s_: fake.d.qpos[fake.qadr[s_]] for s_ in ("right", "left")}
fake.wait_until(3.0)
rpm = max(abs(fake.d.qpos[fake.qadr[s_]] - q0[s_]) / 2.0 * 60 / (2 * math.pi) for s_ in ("right", "left"))
fake.close()
check(f"calibrated table ({U.RPM_AT_100:.1f} rpm at 100 %), legs free, full action = {abs(pct['right'])} %: "
      "legs run at about POLICY_TOP_RPM",
      abs(rpm - U.MAX_RPM) <= 0.05 * U.MAX_RPM and rpm <= U.TRAINED_TOP_RPM[1], f"{rpm:.1f} rpm")
# a POLICY_TOP_RPM outside the trained range is refused
saved_top = C.POLICY_TOP_RPM
for bad in (U.TRAINED_TOP_RPM[1] + 60, U.TRAINED_TOP_RPM[0] - 30):
    if U.V2:
        C.POLICY_TOP_RPM = bad
        try:
            importlib.reload(U)
            refused = False
        except ValueError:
            refused = True
        C.POLICY_TOP_RPM = saved_top
        importlib.reload(U)
        check(f"units.py refuses POLICY_TOP_RPM = {bad:.0f} (outside the trained range)", refused)

print("\n4. Speed-limit warning (addition a): a motor slower than a full action asks for must be reported")
saved_table = C.RPM_AT_PERCENT
C.RPM_AT_PERCENT = [(0, 0.0), (50, 50.0), (100, 100.0)]       # pretend: only 100 rpm at 100 %
importlib.reload(U)
pct, info = U.command(np.array([1.0, 0.0]))
check(f"warning text appears when 100 % gives less than {U.MAX_RPM:.0f} rpm", U.speed_limit_warning() is not None,
      U.speed_limit_warning())
check("a full-speed action is clipped to 100 % and reported", pct["right"] == 100 * C.UPRIGHT_PERCENT_SIGN["right"]
      and "right" in info["clipped"], f"wanted {info['clipped'].get('right', 0):.0f} %")
C.RPM_AT_PERCENT = saved_table
importlib.reload(U)
check(f"no warning with the placeholder table ({U.RPM_AT_100:.0f} rpm at 100 %)", U.speed_limit_warning() is None)

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
