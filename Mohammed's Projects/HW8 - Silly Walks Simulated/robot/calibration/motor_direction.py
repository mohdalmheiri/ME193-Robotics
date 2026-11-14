"""
Calibration 1: which LEGO motor drives which leg, which spin direction walks UPRIGHT, and
which way each encoder counts.

Set-up: the robot held up or on a stand, legs free to spin (they must not touch anything).

How it works, for each LEGO motor in turn (the library's own "left" and "right"):
  1. Spin ONLY that motor at +20 % for 1.5 s (movement_move_tank with the other at 0).
  2. Measure how far its counted encoder position moved (sign = which way it counts).
  3. Ask the person: which leg turned (robot's right or left)? Did it turn like a wheel
     rolling the robot FORWARD? (When the leg points down, its tip sweeps toward the
     robot's BACK.) That is the upright walking direction; the other way flips the robot.
Then it prints, for robot/config.py:
  ROBOT_RIGHT_IS_LEGO     the LEGO side whose motor turned the robot's right leg
  UPRIGHT_PERCENT_SIGN    +1 for a leg if +percent turned it the walking way, else -1
  ENCODER_SIGN            the encoder's direction relative to the simulator's leg angle q.
                          In the simulator the walking direction is NEGATIVE q, so
                          ENCODER_SIGN = sign(encoder change) x (-1 if +% walked, else +1)

Run from the HW8 folder:  ../../.venv/bin/python robot/calibration/motor_direction.py
          rehearse with the simulator:  ... motor_direction.py --fake
"""

import argparse
import math

from _common import FRONT_WORDS, Ask, collect, config_line, motors_stopped, open_robot

TEST_PCT = 20


def measure(robot, ask) -> dict:
    robot.connect()
    found = {}                                  # robot leg -> dict
    with motors_stopped(robot):
        for lego in ("left", "right"):
            before = robot.read_lego()
            robot.send_lego(TEST_PCT if lego == "left" else 0, TEST_PCT if lego == "right" else 0)
            collect(robot, 1.5)
            after = robot.read_lego()
            robot.send_lego(0, 0)
            collect(robot, 0.5)
            moved = {s: after.motors[s].position_deg - before.motors[s].position_deg for s in ("left", "right")}
            print(f"\nLEGO {lego} motor at +{TEST_PCT} %: encoder moved {moved[lego]:+d} deg "
                  f"(other motor {moved['right' if lego == 'left' else 'left']:+d} deg)")
            if abs(moved[lego]) < 30:
                raise RuntimeError("the motor barely turned; is the leg free to spin?")
            leg = "right" if ask("Which leg turned, the robot's RIGHT or LEFT one?", f"leg_{lego}",
                                 ("r", "l")) == "r" else "left"
            forward = ask("Did it turn like a wheel rolling the robot FORWARD (when the leg points "
                          "down, its tip moves toward the robot's BACK)?", f"forward_{lego}") == "y"
            q_dir = -1 if forward else +1                    # simulator: walking = negative q
            found[leg] = {"lego": lego, "upright_sign": +1 if forward else -1,
                          "encoder_sign": int(math.copysign(1, moved[lego])) * q_dir}
    if set(found) != {"right", "left"}:
        raise RuntimeError(f"both motors were reported as the same leg ({list(found)}); please redo")
    robot.close()
    return {"ROBOT_RIGHT_IS_LEGO": found["right"]["lego"],
            "UPRIGHT_PERCENT_SIGN": {s: found[s]["upright_sign"] for s in ("right", "left")},
            "ENCODER_SIGN": {s: found[s]["encoder_sign"] for s in ("right", "left")}}


def fake_oracle(robot):
    """Answers like a person watching the fake robot: from the simulator's truth."""
    def leg_of(lego):
        return "r" if robot.leg_of_lego[lego] == "right" else "l"

    def forward(lego):
        leg = robot.leg_of_lego[lego]
        # +20 % on this motor: did the leg turn the walking (negative q) way?
        return "y" if robot._pct_to_joint_speed(leg, TEST_PCT) < 0 else "n"
    return {"leg_left": lambda: leg_of("left"), "leg_right": lambda: leg_of("right"),
            "forward_left": lambda: forward("left"), "forward_right": lambda: forward("right")}


def report(res):
    print("\nPaste into robot/config.py:")
    config_line(f'ROBOT_RIGHT_IS_LEGO = "{res["ROBOT_RIGHT_IS_LEGO"]}"')
    config_line(f"UPRIGHT_PERCENT_SIGN = {res['UPRIGHT_PERCENT_SIGN']}".replace("'", '"'))
    config_line(f"ENCODER_SIGN = {res['ENCODER_SIGN']}".replace("'", '"'))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="rehearse with the simulator")
    a = ap.parse_args()
    print("Hold the robot up (or put it on a stand) so both legs spin freely.\n" + FRONT_WORDS)
    robot = open_robot(a.fake)
    if a.fake:
        robot.on_stand()
    report(measure(robot, Ask(fake_oracle(robot) if a.fake else None)))
