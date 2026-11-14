"""
Measurement 5: the fixed-speed drift test - both motors at one speed for 10 s, with the legs
in step and out of step - the same test as Julian's hand test and robot/sim_hand_tests.py,
so real and simulated results can be put side by side.

Needs calibrations 1-4 in robot/config.py (it drives the upright way and reads the heading).
Set-up: robot on a large table or floor, a straight line (tape) marking the start direction,
a phone filming from above.

How it works:
  1. The person sets the legs: --legs in  : both legs pointing straight forward, flat (0 deg)
                                --legs out : right leg forward, LEFT leg a quarter turn ahead,
                                             its long arm pointing straight UP (90 deg)
     The script reads both leg angles from the encoders and says how far off they are.
  2. Both motors run at --percent (default 100) in the walking direction for --seconds (10).
     Every sensor message is logged: time, heading (from the motion sensor, deg, + = turned
     left), both leg angles. -> robot/runs/<date>_drift_<in|out>_<percent>.csv
  3. Afterwards it asks for the hand measurements (tape and video): straight-line distance,
     sideways offset from the start line (+ = right), turn angle (+ = left), and prints them
     next to the motion sensor's heading change as a cross-check. They are saved in the same
     folder as <...>.json.
Compare with the simulator: robot/compare_drift.py --real <csv>

Run from the HW8 folder:
  ../../.venv/bin/python robot/calibration/drift_test.py --legs in   [--percent 100] [--fake]
  ../../.venv/bin/python robot/calibration/drift_test.py --legs out
"""

import argparse
import csv
import json
import math
from datetime import datetime

import numpy as np

from _common import ROBOT_DIR, Ask, collect, motors_stopped, open_robot
import config as C  # noqa: E402
import units as U  # noqa: E402
from robot_interface import to_robot_sides  # noqa: E402

LEG_TARGET = {"in": (0.0, 0.0), "out": (0.0, 90.0)}       # (right, left) deg


def wrap(d):
    return (d + 180) % 360 - 180


def measure(robot, ask, legs: str, percent: int, seconds: float):
    robot.connect()
    target = LEG_TARGET[legs]
    ask.enter("Set the legs: " + ("both pointing straight FORWARD, flat." if legs == "in" else
              "RIGHT leg straight forward, flat; LEFT leg a quarter turn ahead, its long arm "
              "pointing straight UP.") + " Put the robot on the start line.", f"legs_{legs}")
    r = to_robot_sides(collect(robot, 0.3)[-1])
    for i, leg in enumerate(("right", "left")):
        now = wrap(math.degrees(U.leg_angle(r, leg)))
        off = wrap(now - target[i])
        print(f"  {leg} leg is at {now:+.0f} deg "
              f"(target {target[i]:+.0f}, off by {off:+.0f})" + ("  <- please adjust" if abs(off) > 10 else ""))
    rows = []
    with motors_stopped(robot):
        robot.send(percent * C.UPRIGHT_PERCENT_SIGN["right"], percent * C.UPRIGHT_PERCENT_SIGN["left"])
        t0 = robot.now()
        for m in collect(robot, seconds):
            m = to_robot_sides(m)
            rows.append([round(m.t - t0, 3), round(math.degrees(U.heading(m)), 2),
                         round(math.degrees(U.leg_angle(m, "right")), 1),
                         round(math.degrees(U.leg_angle(m, "left")), 1), m.yaw])
    robot.close()
    # keep counting past +/-180 deg (the hub's yaw wraps), so 1.5 turns reads 540, not 180
    unwrapped = np.degrees(np.unwrap(np.radians([r_[1] for r_ in rows])))
    for r_, h in zip(rows, unwrapped):
        r_[1] = round(float(h), 2)
    imu_turn = rows[-1][1] - rows[0][1]
    print(f"\nMotion sensor: heading changed {imu_turn:+.1f} deg over {rows[-1][0]:.1f} s")
    hand = {"distance_mm": ask.number("Straight-line distance from start to end point (mm)?", "distance_mm"),
            "sideways_mm": ask.number("Sideways offset from the start line at the end (mm, + = right)?", "sideways_mm"),
            "turn_deg": ask.number("Turn angle from the video (deg, + = turned LEFT)?", "turn_deg")}
    print(f"Hand: distance {hand['distance_mm']:.0f} mm, sideways {hand['sideways_mm']:+.0f} mm, "
          f"turn {hand['turn_deg']:+.0f} deg   (motion sensor: {imu_turn:+.0f} deg)")
    return rows, {"legs": legs, "percent": percent, "seconds": seconds, "imu_turn_deg": imu_turn, **hand}


def save(rows, summary, tag=""):
    out = ROBOT_DIR / "runs"
    out.mkdir(exist_ok=True)
    stem = f"{datetime.now():%Y-%m-%d_%H-%M-%S}_drift_{summary['legs']}_{summary['percent']}{tag}"
    with open(out / f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "heading_deg", "leg_right_deg", "leg_left_deg", "raw_yaw"])
        w.writerows(rows)
    (out / f"{stem}.json").write_text(json.dumps(summary, indent=2))
    print(f"Saved robot/runs/{stem}.csv and .json")
    return out / f"{stem}.csv"


def fake_oracle(robot, legs):
    def place():
        q = [math.radians(x) for x in LEG_TARGET[legs]]
        robot.pose_legs(q[0], q[1])
    t = lambda: robot.truth()
    return {f"legs_{legs}": place,
            "distance_mm": lambda: math.hypot(t()["side_mm"], t()["fwd_mm"]),
            "sideways_mm": lambda: t()["side_mm"],
            # a person counts whole turns on the video; the fake answers with the unwrapped heading
            "turn_deg": lambda: robot.turn_unwrapped_deg}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--legs", choices=["in", "out"], required=True)
    ap.add_argument("--percent", type=int, default=100)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    robot = open_robot(a.fake, start_q=[math.radians(x) for x in LEG_TARGET[a.legs]])
    rows, summary = measure(robot, Ask(fake_oracle(robot, a.legs) if a.fake else None),
                            a.legs, a.percent, a.seconds)
    save(rows, summary, "_fake" if a.fake else "")
