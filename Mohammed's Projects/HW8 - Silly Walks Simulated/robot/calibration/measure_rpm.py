"""
Calibration 3: leg speed (rpm) at 25, 50, 75 and 100 % - and what the hub's own "speed"
report means.

Needs motor_direction.py's results in robot/config.py (it drives both legs the UPRIGHT way).
Set-up: on a stand, legs free (default), or --on-table to measure while walking (under load).

How it works, for each percent:
  1. Both legs at that percent in the walking direction; wait 1 s to reach speed.
  2. For 3 s, rpm = (counted encoder change in degrees / 360) / 3 s x 60, per leg.
  3. Also averages the hub's speed report (percent) per leg.
Prints:
  - RPM_AT_PERCENT for robot/config.py (the average of both legs) and RPM_MEASURED = True
  - the left/right difference (the training randomizes each side by +/-10 %)
  - what the speed report means: if it matches the measured rpm as a percent of the
    100 % speed, it reports the ACTUAL speed; if it just equals the command, the TARGET
  - a WARNING if the speed at 100 % is outside what the policy was trained for
    (policy_meta.json: v1 assumed exactly 120 rpm; v2 was trained for a range)

Run from the HW8 folder:  ../../.venv/bin/python robot/calibration/measure_rpm.py [--on-table] [--fake]
"""

import argparse

import numpy as np

from _common import collect, config_line, motors_stopped, open_robot   # (first: sets the path)
import config as C  # noqa: E402
import units as U  # noqa: E402
from robot_interface import lego_side  # noqa: E402

PERCENTS = (25, 50, 75, 100)


def measure(robot, ask=None) -> dict:
    robot.connect()
    rows = []
    with motors_stopped(robot):
        for pct in PERCENTS:
            robot.send(pct * C.UPRIGHT_PERCENT_SIGN["right"], pct * C.UPRIGHT_PERCENT_SIGN["left"])
            collect(robot, 1.0)
            msgs = collect(robot, 3.0)
            dt = msgs[-1].t - msgs[0].t
            rpm, rep = {}, {}
            for leg in ("right", "left"):
                ls = lego_side(leg)                       # its LEGO motor (config)
                turned = msgs[-1].motors[ls].position_deg - msgs[0].motors[ls].position_deg
                rpm[leg] = abs(turned) / 360 / dt * 60
                rep[leg] = float(np.mean([abs(r_.motors[ls].speed_pct) for r_ in msgs]))
            rows.append((pct, rpm, rep))
            print(f"{pct:3d} %: right {rpm['right']:6.1f} rpm, left {rpm['left']:6.1f} rpm   "
                  f"(hub speed report: right {rep['right']:5.1f} %, left {rep['left']:5.1f} %)")
    robot.close()
    return {"rows": rows}


def report(res):
    rows = res["rows"]
    table = [(0, 0.0)] + [(p, round((r["right"] + r["left"]) / 2, 1)) for p, r, _ in rows]
    top = table[-1][1]
    diff = [abs(r["right"] - r["left"]) / ((r["right"] + r["left"]) / 2) * 100 for _, r, _ in rows]
    print(f"\nLeft/right speed difference: {max(diff):.1f} % at most "
          f"(training randomizes each side by +/-{(U.META['randomization']['motor_speed_scale'][1] - 1) * 100:.0f} %)")
    # what does the hub's speed report mean?
    p100 = rows[-1]
    actual_pct = [100 * (p100[1][s]) / top for s in ("right", "left")]
    print(f"Hub speed report at 100 %: {np.mean(list(p100[2].values())):.0f} %; measured speed as a "
          f"percent of the 100 % speed: {np.mean(actual_pct):.0f} %. "
          "Compare the lower percents above: if the report follows the MEASURED speed it is the "
          "actual speed (usable with LEG_SPEED_SOURCE = \"hub_speed\"); if it always equals the "
          "command, it is only the target.")
    meta = U.META
    if "top_speed_rpm_range" in meta:
        lo, hi = meta["top_speed_rpm_range"]
        if not lo <= top <= hi:
            print(f"\n*** WARNING: {top:.0f} rpm at 100 % is OUTSIDE the {lo:.0f}-{hi:.0f} rpm the "
                  "policy was trained for. Retrain with the range recentred on this value. ***")
        else:
            print(f"\nOK: {top:.0f} rpm at 100 % is inside the trained range {lo:.0f}-{hi:.0f} rpm.")
    elif top < 0.97 * meta["max_speed_rpm"]:          # 3 % allowance for measurement rounding
        print(f"\n*** WARNING: the motor reaches only {top:.0f} rpm at 100 %, but this policy was "
              f"trained for up to {meta['max_speed_rpm']:.0f} rpm. Commands above {top:.0f} rpm will "
              "be clipped. Retrain with MAX_SPEED_RPM set to the measured value. ***")
    print("\nPaste into robot/config.py:")
    config_line(f"RPM_AT_PERCENT = {table}")
    config_line("RPM_MEASURED = True")
    return table


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--on-table", action="store_true", help="measure while walking on the table")
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    print("Robot " + ("on the table, with room to walk ~1 m." if a.on_table else
                      "held up / on a stand, legs free to spin."))
    robot = open_robot(a.fake)
    if a.fake and not a.on_table:
        robot.on_stand()
    report(measure(robot))
