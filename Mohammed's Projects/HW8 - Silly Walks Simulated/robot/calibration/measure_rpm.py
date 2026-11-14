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


def report(res, paste=True):
    """Prints the checks; paste=False leaves out the lines to paste (calibrate.py writes them)."""
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
        # v2: the action is turned into an rpm inside the trained range (config.POLICY_TOP_RPM)
        # BEFORE it becomes a percent, so a FASTER motor is fine (it just uses lower percents).
        # The motor only has to be able to reach the chosen top speed.
        lo, hi = meta["top_speed_rpm_range"]
        if top < lo:
            print(f"\n*** WARNING: {top:.0f} rpm at 100 % is below the slowest top speed the policy "
                  f"trained with ({lo:.0f} rpm). Retrain with the range recentred on this value. ***")
        elif top < 0.97 * C.POLICY_TOP_RPM:
            print(f"\n*** WARNING: {top:.0f} rpm at 100 % is below config.POLICY_TOP_RPM = "
                  f"{C.POLICY_TOP_RPM:.0f}: set POLICY_TOP_RPM to {min(top, hi):.0f} or less. ***")
        else:
            print(f"\nOK: the motor reaches {top:.0f} rpm at 100 %; a full action asks for "
                  f"POLICY_TOP_RPM = {C.POLICY_TOP_RPM:.0f} rpm (trained range {lo:.0f}-{hi:.0f}), "
                  f"about {100 * C.POLICY_TOP_RPM / top:.0f} % power.")
    if paste:
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
