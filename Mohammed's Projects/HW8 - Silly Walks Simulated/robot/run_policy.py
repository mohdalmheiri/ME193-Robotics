"""
Drive a robot with the trained policy: read sensors -> policy -> motor speeds, 20 times a
second. The same loop drives the real LEGO robot and the simulator's FakeRobot.

  python robot/run_policy.py --fake                 FakeRobot (fast, no waiting)
  python robot/run_policy.py --fake --realtime      FakeRobot at real speed (a rehearsal)
  python robot/run_policy.py --real                 the real Double Motor over Bluetooth
  options: --seconds 20  --seed 0 (fake robot number)  --name label-for-the-log

How one decision works (every 0.05 s on the robot's clock):
  1. wait until the next decision time
  2. SAFETY checks (any failure -> motors stop, run ends, the reason is printed and logged):
       - connection lost          (robot.connected is False, or a read/send fails)
       - stale sensors            (no new sensor message for config.STALE_SENSOR_S = 0.3 s;
                                   a frozen Bluetooth link can still look "connected")
       - tipped over              (body tilted past the training's flip angle, 70 deg)
       - time limit               (--seconds; the normal end of a run)
       - Ctrl-C                   (KeyboardInterrupt)
     The final stop is in a `finally:` block, so it also runs if the code crashes.
     Honest limit: after a LOST connection the laptop cannot reach the hub to stop it; the
     hub's own behaviour then decides (to be checked at the robot session, on a stand).
  3. units.observation(): hub readings -> the 16 policy inputs
  4. policy -> 2 actions -> units.command(): whole percents per leg; commands above 100 %
     are clipped, counted, logged, and warned about
  5. send both speeds in one message
Every decision is one row in robot/runs/<date>_<fake|real>_<name>.csv (ignored by git):
time, raw hub readings, the 16 inputs, actions, percents, clipping, and for FakeRobot the
true drift/heading/forward distance (blank for the real robot).
"""

import argparse
import csv
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROBOT_DIR))
import config as C  # noqa: E402
import units as U  # noqa: E402
from policy import Policy  # noqa: E402

RUNS_DIR = ROBOT_DIR / "runs"
FLIP_DEG = U.META["flip_angle_deg"]
OBS_NAMES = (["tilt_x", "tilt_y", "tilt_z", "gyro_x", "gyro_y", "gyro_z", "head_sin", "head_cos",
              "leg_sin_r", "leg_sin_l", "leg_cos_r", "leg_cos_l", "leg_speed_r", "leg_speed_l",
              "last_cmd_r", "last_cmd_l"])
COLUMNS = (["t", "msg_count", "msg_t", "ax_mg", "ay_mg", "az_mg", "gx_dps", "gy_dps", "gz_dps",
            "yaw", "pitch", "roll", "abs_r", "abs_l", "pos_r", "pos_l", "speed_pct_r", "speed_pct_l"]
           + ["in_" + n for n in OBS_NAMES]
           + ["action_r", "action_l", "pct_r", "pct_l", "wanted_rpm_r", "wanted_rpm_l",
              "clipped_pct_r", "clipped_pct_l", "true_side_mm", "true_fwd_mm", "true_heading_deg"])


def startup_warnings():
    """Things the person at the robot must know before it moves."""
    w = []
    if not C.RPM_MEASURED:
        w.append("NOTE: the rpm-per-percent table in config.py is a PLACEHOLDER (not measured "
                 "yet). Run calibration/measure_rpm.py first on the real robot.")
    if (msg := U.speed_limit_warning()):
        w.append(msg)
    return w


def tilt_deg(tilt_vec) -> float:
    """Angle between the measured gravity direction and straight down (deg)."""
    return math.degrees(math.acos(max(-1.0, min(1.0, -float(tilt_vec[2])))))


def run(robot, seconds: float, log_path: Path | None, policy=None, on_decision=None,
        quiet: bool = False) -> dict:
    """Run the loop on `robot` (any RobotInterface). Returns a summary dict.

    on_decision(k, robot) is an optional hook called before each decision (the tests use
    it to pull the plug, freeze the sensors, tip the robot or press Ctrl-C).
    """
    say = (lambda *a: None) if quiet else print
    policy = policy or Policy()
    for w in startup_warnings():
        say(w)
    rows, reason, clipped = [], "time limit reached", 0
    last_cmd = np.zeros(2)                # training starts every episode with "previous" = 0
    legs = U.LegSpeed()
    robot.connect()
    t0 = robot.now()
    k = 0
    n_decisions = round(seconds / U.META["decision_dt_s"])     # 20 s -> 400 decisions
    try:
        while True:
            robot.wait_until(t0 + k * U.META["decision_dt_s"])
            if on_decision:
                on_decision(k, robot)
            now = robot.now()
            # ---- safety checks
            if k >= n_decisions:          # counted, so float rounding can't add a step
                break
            if not robot.connected:
                reason = "connection lost"
                break
            try:
                r = robot.read()
            except ConnectionError:
                reason = "connection lost (read failed)"
                break
            if now - r.t > C.STALE_SENSOR_S:
                reason = f"stale sensors (no new message for {now - r.t:.2f} s)"
                break
            obs = U.observation(r, legs.update(r), last_cmd)
            if tilt_deg(obs[:3]) > FLIP_DEG:
                reason = f"tipped over ({tilt_deg(obs[:3]):.0f} deg > {FLIP_DEG:.0f} deg)"
                break
            # ---- decide and act
            action = policy(obs)
            pct, info = U.command(action)
            if info["clipped"]:
                clipped += 1
                if clipped == 1:
                    say(f"WARNING t={now - t0:.2f}s: the policy asked for more than 100 % "
                        f"({info['clipped']}); clipped to 100 %. Every clip is logged.")
            try:
                robot.send(pct["right"], pct["left"])
            except ConnectionError:
                reason = "connection lost (send failed)"
                break
            last_cmd = np.clip(action, -1, 1)
            truth = robot.truth() if hasattr(robot, "truth") else {}
            rows.append([round(now - t0, 4), r.count, round(r.t - t0, 4), *r.accel_mg, *r.gyro_dps,
                         r.yaw, r.pitch, r.roll, r.motors["right"].absolute_deg,
                         r.motors["left"].absolute_deg, r.motors["right"].position_deg,
                         r.motors["left"].position_deg, r.motors["right"].speed_pct,
                         r.motors["left"].speed_pct, *np.round(obs, 5), *np.round(action, 5),
                         pct["right"], pct["left"], round(info["wanted_rpm"]["right"], 2),
                         round(info["wanted_rpm"]["left"], 2),
                         round(info["clipped"].get("right", 0), 1), round(info["clipped"].get("left", 0), 1),
                         *(round(truth[k_], 2) if truth else "" for k_ in ("side_mm", "fwd_mm", "heading_deg"))])
            k += 1
    except KeyboardInterrupt:
        reason = "Ctrl-C"
    finally:
        # Always try to stop the motors, whatever happened above.
        try:
            robot.stop()
        except Exception as e:                            # noqa: BLE001
            say(f"could not send stop ({e}); the hub's own safety must stop the motors")
        robot.close()
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(COLUMNS)
                wr.writerows(rows)
    summary = {"reason": reason, "decisions": len(rows), "clipped_decisions": clipped,
               "seconds": round(robot.now() - t0, 3), "log": str(log_path) if log_path else None}
    if hasattr(robot, "truth"):
        summary["truth"] = robot.truth()
    say(f"Stopped: {reason}. {len(rows)} decisions, {clipped} with clipped commands."
        + (f" Log: {log_path.relative_to(ROBOT_DIR.parent)}" if log_path else ""))
    return summary


def main():
    p = argparse.ArgumentParser(description="Drive the robot with the trained policy")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fake", action="store_true", help="simulated robot (FakeRobot)")
    g.add_argument("--real", action="store_true", help="real LEGO Double Motor")
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--seed", type=int, default=0, help="which random fake robot")
    p.add_argument("--realtime", action="store_true", help="FakeRobot at real speed")
    p.add_argument("--name", default="", help="label added to the log file name")
    a = p.parse_args()
    if a.seconds > C.MAX_RUN_S:
        sys.exit(f"--seconds {a.seconds} is above the safety limit config.MAX_RUN_S = {C.MAX_RUN_S}")
    if a.fake:
        from fake_robot import FakeRobot
        robot, kind = FakeRobot(seed=a.seed, realtime=a.realtime), f"fake{a.seed}"
    else:
        from real_robot import RealRobot
        robot, kind = RealRobot(), "real"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log = RUNS_DIR / f"{stamp}_{kind}{'_' + a.name if a.name else ''}.csv"
    s = run(robot, a.seconds, log)
    if "truth" in s:
        t = s["truth"]
        print(f"Fake robot truth: heading {t['heading_deg']:+.1f} deg, sideways {t['side_mm']:+.0f} mm, "
              f"forward {t['fwd_mm']:.0f} mm")


if __name__ == "__main__":
    main()
