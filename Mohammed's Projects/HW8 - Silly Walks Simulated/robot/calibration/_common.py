"""
Shared pieces of the calibration scripts.

  open_robot(fake)   RealRobot (the Double Motor), or a FakeRobot for rehearsing/testing
  Ask                asks the person at the robot a question; with a FakeRobot, an "oracle"
                     answers from the simulator's truth, so the scripts can be tested end
                     to end without the robot
  collect()          gathers every NEW sensor message for a while (deduplicated by the
                     message counter), at the LEGO level (no config assumptions)
  motors_stopped()   a `with` block that always stops the motors at the end, also on
                     Ctrl-C or an error
  config_line()      prints a line to paste into robot/config.py

Every calibration script computes its result from RAW hub readings only (read_lego), never
through units.py, so it cannot inherit the assumption it is measuring.
"""

import contextlib
import sys
from pathlib import Path

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))

FRONT_WORDS = ("FRONT = the end of the robot next to the motor axle (the body sticks out "
               "mostly BEHIND the axle). Legs at 0 deg = pointing straight forward, flat, "
               "with the long arm (48 mm) in front of the axle.")


def open_robot(fake: bool, **fake_kwargs):
    if fake:
        from fake_robot import FakeRobot
        # armature 2e-4: v2's motor inertia (v1's 1e-5 makes free legs chatter at ~81 rpm)
        return FakeRobot(**{"seed": 0, "randomize": False, "start_q": [0.0, 0.0], "start_yaw": 0.0,
                            "armature": 2e-4, **fake_kwargs})
    from real_robot import RealRobot
    return RealRobot()


class Ask:
    """ask(question, key) -> answer string. Real robot: typed by the person. Fake: oracle[key]()."""

    def __init__(self, oracle: dict | None = None):
        self.oracle = oracle

    def __call__(self, question: str, key: str, choices=("y", "n")) -> str:
        if self.oracle is not None:
            ans = self.oracle[key]()
            print(f"{question} [{'/'.join(choices)}]  -> (fake robot answers) {ans}")
            return ans
        while True:
            ans = input(f"{question} [{'/'.join(choices)}] ").strip().lower()
            if ans in choices:
                return ans
            print(f"  please type one of: {', '.join(choices)}")

    def number(self, question: str, key: str) -> float:
        """Ask for a measured number (blank = not measured -> NaN)."""
        if self.oracle is not None:
            ans = float(self.oracle[key]())
            print(f"{question}  -> (fake robot answers) {ans:.0f}")
            return ans
        while True:
            txt = input(f"{question} (blank = skip) ").strip()
            if not txt:
                return float("nan")
            try:
                return float(txt)
            except ValueError:
                print("  please type a number")

    def enter(self, instruction: str, key: str | None = None):
        """Wait until the person has done something; with a FakeRobot, the oracle does it."""
        if self.oracle is not None:
            print(f"{instruction}  -> (fake robot does it)")
            if key:
                self.oracle[key]()
            return
        input(f"{instruction}  Press Enter when done. ")


def collect(robot, seconds: float, step: float = 0.01) -> list:
    """Every new sensor message for `seconds`, LEGO level. Returns a list of Readings."""
    out, last = [], -1
    t_end = robot.now() + seconds
    while robot.now() < t_end:
        robot.wait_until(robot.now() + step)
        r = robot.read_lego()
        if r.count != last:
            out.append(r)
            last = r.count
    return out


@contextlib.contextmanager
def motors_stopped(robot):
    try:
        yield
    finally:
        try:
            robot.send_lego(0, 0)
            robot.stop()
        except Exception as e:                               # noqa: BLE001
            print(f"(could not send stop: {e})")


def config_line(text: str):
    print(f"    {text}")
