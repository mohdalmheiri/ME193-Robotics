"""
Calibration 2: what each encoder reads when its leg points straight forward, flat (the
simulator's leg angle 0).

Needs ROBOT_RIGHT_IS_LEGO from motor_direction.py already in robot/config.py.
Set-up: robot on the table or held, motors OFF.

How it works:
  1. Asks the person to turn BOTH legs by hand to point straight forward, flat: the long
     arm (48 mm) in front of the axle, parallel to the table.
  2. Averages the absolute encoder position (0..359 deg) over 0.5 s of sensor messages,
     per leg (averaging angles as directions, so 359 and 1 average to 0, not 180).
  3. Prints LEG_ZERO_DEG for robot/config.py.
  4. Checks: the person then turns ONE leg (the right one) a quarter turn so its tip
     points straight UP; the encoder should change by about 90 deg (prints the change).

Run from the HW8 folder:  ../../.venv/bin/python robot/calibration/leg_zero.py   [--fake]
"""

import argparse
import math

import numpy as np

from _common import FRONT_WORDS, Ask, collect, config_line, open_robot
from robot_interface import lego_side


def circ_mean_deg(values) -> float:
    a = np.radians(values)
    return math.degrees(math.atan2(np.sin(a).mean(), np.cos(a).mean())) % 360


def measure(robot, ask) -> dict:
    robot.connect()
    robot.send_lego(0, 0)
    ask.enter("Turn BOTH legs by hand so they point straight FORWARD, flat (long arm in "
              "front of the axle, parallel to the table).", "legs_forward")
    msgs = collect(robot, 0.5)
    zero = {leg: round(circ_mean_deg([m.motors[lego_side(leg)].absolute_deg for m in msgs]), 1)
            for leg in ("right", "left")}
    ask.enter("Now turn only the RIGHT leg a quarter turn so its long arm points straight UP.",
              "right_up")
    msgs = collect(robot, 0.5)
    up = circ_mean_deg([m.motors[lego_side("right")].absolute_deg for m in msgs])
    change = (up - zero["right"] + 180) % 360 - 180
    robot.close()
    print(f"\nRight leg: forward reads {zero['right']:.1f} deg, pointing up reads {up:.1f} deg "
          f"(change {change:+.0f} deg; expect about +/-90)")
    return {"LEG_ZERO_DEG": zero, "quarter_turn_change_deg": change}


def fake_oracle(robot):
    return {"legs_forward": lambda: robot.pose_legs(0.0, 0.0),
            # "up" = the long arm pointing up: in the simulator that is q = +90 deg
            "right_up": lambda: robot.pose_legs(math.pi / 2, 0.0)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    print(FRONT_WORDS)
    robot = open_robot(a.fake)
    res = measure(robot, Ask(fake_oracle(robot) if a.fake else None))
    print("\nPaste into robot/config.py:")
    config_line(f'LEG_ZERO_DEG = {{"right": {res["LEG_ZERO_DEG"]["right"]}, "left": {res["LEG_ZERO_DEG"]["left"]}}}')
