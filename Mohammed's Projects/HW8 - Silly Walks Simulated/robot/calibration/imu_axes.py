"""
Calibration 4: how the hub's motion sensor is mounted, and what its numbers mean.

Set-up: robot on the table, motors off. Four short poses, each held still for 1 s:
  A  flat on the table
  B  FRONT down: lift the BACK end so the robot leans forward, about 30-60 deg
  C  RIGHT side down: lift the LEFT side, about 30-60 deg
  D  flat again; after pressing Enter, turn it by hand about a QUARTER TURN to the LEFT
     (counter-clockwise seen from above) within ~2 s, then hold still

How it works (only raw hub readings; at rest the accelerometer reads exactly "up"):
  A: the accelerometer axis that reads about +1000 milli-g (or -1000) is the robot's UP axis.
  B: leaning forward, gravity tips toward the front, so the accelerometer gains a NEGATIVE
     reading along the robot's FRONT axis -> which hub axis is "front", and its sign.
     Right = front x up (right-handed axes) -> BODY_FROM_HUB.
  A, B, C: the hub reports pitch/roll about ITS OWN axes. units.py turns them into gravity
     with one fixed formula, so the right settings (PITCH_ROLL_SWAPPED, ANGLE_UNIT_DEG,
     PITCH_SIGN, ROLL_SIGN) are those for which that formula reproduces the gravity the
     accelerometer measures in all three resting poses: all 16 combinations are tried and
     the best kept (with a warning if even the best is more than 5 deg off).
  D: yaw change sign -> YAW_SIGN (a LEFT turn should read positive); the gyroscope about
     the up axis, added up over the turn (deg/s x seconds), must give the same angle ->
     GYRO_SIGN, and a check that the gyro really is in deg/s.

Run from the HW8 folder:  ../../.venv/bin/python robot/calibration/imu_axes.py   [--fake]
"""

import argparse
import math

import numpy as np

from _common import FRONT_WORDS, Ask, collect, config_line, open_robot
from units import axis_map, gravity_from_pitch_roll


def mean_accel(msgs):
    return np.mean([m.accel_mg for m in msgs], axis=0)


def g_meas(msgs):
    """Gravity direction in HUB axes, measured at rest (= minus the accelerometer reading)."""
    a = mean_accel(msgs)
    return -a / np.linalg.norm(a)


def circ_mean(deg_values) -> float:
    """Average of angles as directions (so 179 and -179 average to 180, not 0)."""
    r = np.radians(deg_values)
    return math.degrees(math.atan2(np.sin(r).mean(), np.cos(r).mean()))


def spec(v):
    """A unit vector along one hub axis -> '+x' / '-y' / ..."""
    k = int(np.argmax(np.abs(v)))
    return ("+" if v[k] > 0 else "-") + "xyz"[k]


def fit_pitch_roll(poses):
    """Try every convention; return (mean error deg, swapped, unit, pitch sign, roll sign)."""
    best = None
    for swapped in (False, True):
        for unit in (1.0, 0.1):
            for ps in (+1, -1):
                for rs in (+1, -1):
                    err = 0.0
                    for msgs in poses:
                        f_p = [(m.roll if swapped else m.pitch) * unit for m in msgs]
                        f_r = [(m.pitch if swapped else m.roll) * unit for m in msgs]
                        g = gravity_from_pitch_roll(math.radians(ps * circ_mean(f_p)),
                                                    math.radians(rs * circ_mean(f_r)))
                        err += math.degrees(math.acos(max(-1.0, min(1.0, float(g @ g_meas(msgs))))))
                    if best is None or err < best[0]:
                        best = (err, swapped, unit, ps, rs)
    return (best[0] / len(poses),) + best[1:]


def measure(robot, ask) -> dict:
    robot.connect()
    robot.send_lego(0, 0)
    res, warn = {}, []

    ask.enter("A: put the robot FLAT on the table and keep it still.", "flat")
    A = collect(robot, 1.0)
    a0 = mean_accel(A)
    k_up = int(np.argmax(np.abs(a0)))
    ez = np.zeros(3)
    ez[k_up] = math.copysign(1, a0[k_up])                     # robot's up axis, in hub axes
    if abs(np.linalg.norm(a0) - 1000) > 150:
        warn.append(f"at rest the accelerometer reads {np.linalg.norm(a0):.0f}, not ~1000: is it milli-g?")

    ask.enter("B: lift the BACK so the robot leans FORWARD (front down) ~30-60 deg; hold still.", "nose_down")
    B = collect(robot, 1.0)
    a1 = mean_accel(B).copy()
    a1[k_up] = 0.0
    k_f = int(np.argmax(np.abs(a1)))
    ey = np.zeros(3)
    ey[k_f] = -math.copysign(1, a1[k_f])                      # robot's front: reading went NEGATIVE
    ex = np.cross(ey, ez)                                     # robot's right = front x up
    body_from_hub = {"x": spec(ex), "y": spec(ey), "z": spec(ez)}
    M = axis_map(body_from_hub)

    ask.enter("C: lift the LEFT side so the RIGHT side is down ~30-60 deg; hold still.", "right_down")
    Cm = collect(robot, 1.0)

    err, swapped, unit, ps, rs = fit_pitch_roll([A, B, Cm])
    if err > 5:
        warn.append(f"pitch/roll never matched the accelerometer well (best: {err:.1f} deg off on "
                    'average); consider TILT_SOURCE = "accel"')
    res.update(BODY_FROM_HUB=body_from_hub, PITCH_ROLL_SWAPPED=swapped, ANGLE_UNIT_DEG=unit,
               PITCH_SIGN=ps, ROLL_SIGN=rs)

    def lean(msgs):
        """The ROBOT's pitch (+ = front up) and roll (+ = right down), deg, from gravity."""
        g = M @ g_meas(msgs)
        return math.degrees(math.asin(-g[1])), math.degrees(math.atan2(g[0], -g[2]))

    pitch_b, _ = lean(B)
    _, roll_c = lean(Cm)
    print(f"\nB: robot leaned {pitch_b:+.0f} deg (front down is negative); C: {roll_c:+.0f} deg right "
          f"side down. The hub's pitch/roll match gravity to {err:.1f} deg on average.")
    if pitch_b > -15:
        warn.append(f"the front-down lean measured {pitch_b:+.0f} deg: expected -30..-60")
    if roll_c < 15:
        warn.append(f"the right-side-down lean measured {roll_c:+.0f} deg: expected +30..60; the "
                    "right/left axis may be wrong (or the left side was lowered)")

    ask.enter("D: put it FLAT again, still.", "flat_again")
    y0 = circ_mean([m.yaw * unit for m in collect(robot, 0.5)])
    ask.enter("Now turn it about a QUARTER TURN to the LEFT (counter-clockwise from above) "
              "within ~2 s, then hold still.", "turn_left")
    D = collect(robot, 3.5)
    y1 = circ_mean([m.yaw * unit for m in D[-10:]])
    d_yaw = (y1 - y0 + 180) % 360 - 180
    gz = [float((M @ np.array(m.gyro_dps, dtype=float))[2]) for m in D]   # about the robot's up axis
    ts = [m.t for m in D]
    turned_gyro = float(np.sum(np.array(gz[:-1]) * np.diff(ts)))         # deg/s x s
    res["YAW_SIGN"] = int(math.copysign(1, d_yaw))
    res["GYRO_SIGN"] = int(math.copysign(1, turned_gyro))
    if not 0.7 < abs(turned_gyro) / max(abs(d_yaw), 1e-9) < 1.4:
        warn.append(f"gyro adds up to {turned_gyro:+.0f} but yaw changed {d_yaw:+.0f} deg: the gyro "
                    "may not be in deg/s")
    print(f"D: yaw changed {d_yaw:+.0f} deg; gyro about the up axis adds up to {turned_gyro:+.0f} deg")
    robot.close()
    res["warnings"] = warn
    return res


def fake_oracle(robot):
    """A 'person' moving the fake robot: holds it in each pose (physics paused)."""
    return {"flat": lambda: robot.hold_pose(0, 0, 0),
            "nose_down": lambda: robot.hold_pose(pitch_deg=-40),
            "right_down": lambda: robot.hold_pose(roll_deg=45),
            "flat_again": lambda: robot.hold_pose(0, 0, 0),
            "turn_left": lambda: robot.hold_turn(90, 1.5)}


def report(res):
    for w in res["warnings"]:
        print("  WARNING:", w)
    print("\nPaste into robot/config.py:")
    config_line(f"BODY_FROM_HUB = {res['BODY_FROM_HUB']}".replace("'", '"'))
    config_line(f"ANGLE_UNIT_DEG = {res['ANGLE_UNIT_DEG']}")
    for k in ("PITCH_SIGN", "ROLL_SIGN", "YAW_SIGN", "GYRO_SIGN"):
        config_line(f"{k} = {res[k]:+d}")
    config_line(f"PITCH_ROLL_SWAPPED = {res['PITCH_ROLL_SWAPPED']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    print(FRONT_WORDS)
    robot = open_robot(a.fake)
    report(measure(robot, Ask(fake_oracle(robot) if a.fake else None)))
