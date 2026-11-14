"""
Proof that the calibration scripts FIND the robot's real wiring and sensor conventions,
including when every guess in config.py is wrong.

How it works:
  1. A FakeRobot is given a hidden "true hub" that differs from config.py's defaults in
     everything calibration measures: LEGO left/right swapped, one motor reversed, both
     encoders counting differently, odd leg zeros (200 and 37 deg), a slower motor (95 rpm
     at 100 %), the motion sensor mounted turned and/or upside down, angles in TENTHS of a
     degree, flipped pitch/yaw/gyro signs, pitch and roll fields swapped. Sensor noise on.
  2. The four calibration scripts run against it exactly as at the robot, with an "oracle"
     answering the questions the way a person watching would (from the simulator's truth).
     After each script, its printed values are "pasted" into config (as the checklist says).
  3. Every recovered value is compared with the hidden truth.
  4. End to end: with the recovered config, the control loop drives this oddly wired robot
     for 10 s and must walk (not flip, heading within 20 deg). With the WRONG (default)
     config, the same robot does not (shows the calibration is what makes it work).
  Two hub truths are tested (sensor turned 90 deg; sensor upside down).

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_calibration.py
"""

import copy
import importlib
import math
import sys
from pathlib import Path

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))
sys.path.insert(0, str(ROBOT_DIR / "calibration"))
import config as C  # noqa: E402
import units as U  # noqa: E402
import imu_axes, leg_zero, measure_rpm, motor_direction  # noqa: E402,E401
from _common import Ask  # noqa: E402
from fake_robot import FakeRobot, HUB_KEYS  # noqa: E402
from run_policy import run  # noqa: E402

DEFAULTS = {k: copy.deepcopy(getattr(C, k)) for k in HUB_KEYS + ("RPM_MEASURED",)}
from _fake_hubs import FAKE_HUBS  # noqa: E402

# the same two mis-wired hubs calibrate.py's test and --fake rehearsal use
TRUTHS = {"sensor turned 90 deg": FAKE_HUBS["turned-90"], "sensor upside down": FAKE_HUBS["upside-down"]}
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ({detail})" if detail else ""))


def set_config(values: dict):
    for k, v in values.items():
        setattr(C, k, copy.deepcopy(v))
    importlib.reload(U)                     # units.py rebuilds its axis matrix / rpm table


def fake(truth, **kw):
    return FakeRobot(**{"seed": 4, "randomize": False, "start_q": [0.0, 0.0], "start_yaw": 0.0,
                        "armature": 2e-4, "hub": truth, **kw})


def walk_test(truth) -> dict:
    """10 s of the trained policy on this hub (lopsided-free robot), true outcome."""
    r = FakeRobot(seed=5, randomize=False, start_yaw=0.3, armature=2e-4, hub=truth)
    s = run(r, 10.0, None, quiet=True)
    return {"reason": s["reason"], **s["truth"]}


for name, truth in TRUTHS.items():
    print(f"\n=== Hidden hub: {name}")
    set_config(DEFAULTS)
    wrong = walk_test(truth)

    r = fake(truth)
    r.on_stand()
    got = motor_direction.measure(r, Ask(motor_direction.fake_oracle(r)))
    for k in ("ROBOT_RIGHT_IS_LEGO", "UPRIGHT_PERCENT_SIGN", "ENCODER_SIGN"):
        check(f"motor_direction finds {k}", got[k] == truth[k], f"found {got[k]}, true {truth[k]}")
    set_config({k: got[k] for k in ("ROBOT_RIGHT_IS_LEGO", "UPRIGHT_PERCENT_SIGN", "ENCODER_SIGN")})

    r = fake(truth)
    got = leg_zero.measure(r, Ask(leg_zero.fake_oracle(r)))
    for leg in ("right", "left"):
        # what the encoder truly reads at leg-forward, including the fake's own +/-2 deg
        # encoder calibration error (a real robot has one too; calibration absorbs it)
        expect = (truth["LEG_ZERO_DEG"][leg] + truth["ENCODER_SIGN"][leg] * math.degrees(r.leg_calib[leg])) % 360
        err = (got["LEG_ZERO_DEG"][leg] - expect + 180) % 360 - 180
        check(f"leg_zero finds the {leg} leg's zero", abs(err) < 1.5,
              f"found {got['LEG_ZERO_DEG'][leg]:.1f}, true {expect:.1f}")
    check("leg_zero's quarter-turn check reads about 90 deg", abs(abs(got["quarter_turn_change_deg"]) - 90) < 5,
          f"{got['quarter_turn_change_deg']:+.0f}")
    set_config({"LEG_ZERO_DEG": got["LEG_ZERO_DEG"]})

    r = fake(truth)
    r.on_stand()
    rows = measure_rpm.measure(r)["rows"]
    table = measure_rpm.report({"rows": rows})
    true_top = truth["RPM_AT_PERCENT"][-1][1]
    check("measure_rpm finds the speed at 100 %", abs(table[-1][1] - true_top) / true_top < 0.02,
          f"found {table[-1][1]:.1f}, true {true_top:.1f}")
    set_config({"RPM_AT_PERCENT": table, "RPM_MEASURED": True})

    r = fake(truth)
    got = imu_axes.measure(r, Ask(imu_axes.fake_oracle(r)))
    for k in ("BODY_FROM_HUB", "ANGLE_UNIT_DEG", "PITCH_SIGN", "ROLL_SIGN", "YAW_SIGN", "GYRO_SIGN",
              "PITCH_ROLL_SWAPPED"):
        check(f"imu_axes finds {k}", got[k] == truth[k], f"found {got[k]}, true {truth[k]}")
    check("imu_axes raises no warnings", not got["warnings"], "; ".join(got["warnings"]))
    set_config({k: got[k] for k in ("BODY_FROM_HUB", "ANGLE_UNIT_DEG", "PITCH_SIGN", "ROLL_SIGN",
                                    "YAW_SIGN", "GYRO_SIGN", "PITCH_ROLL_SWAPPED")})

    right = walk_test(truth)
    check("with the CALIBRATED config the policy walks this robot (10 s, no flip, heading < 20 deg)",
          right["reason"] == "time limit reached" and abs(right["heading_deg"]) < 20 and right["fwd_mm"] > 100,
          f"{right['reason']}, heading {right['heading_deg']:+.0f} deg, forward {right['fwd_mm']:.0f} mm")
    check("with the DEFAULT (wrong) config it does not",
          not (wrong["reason"] == "time limit reached" and abs(wrong["heading_deg"]) < 20 and wrong["fwd_mm"] > 100),
          f"{wrong['reason']}, heading {wrong['heading_deg']:+.0f} deg, forward {wrong['fwd_mm']:.0f} mm")

set_config(DEFAULTS)
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
