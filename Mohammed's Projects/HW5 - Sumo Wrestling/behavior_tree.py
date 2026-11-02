"""The sumo wrestler's policy: a behavior tree.

Pure logic, no hardware, so it can be tested on its own (see test_behavior_tree.py).
Every tick, the branches are checked top to bottom and the first one that applies wins:

    1. OUT        the "out" button was pressed     -> stop, play the sad song, stay stopped
    2. NO_EDGE    the color sensor isn't working   -> stop (unsafe to drive without it)
    3. EDGE_PUSH  on the tape, but opponent close
                  + human charging                 -> full power forward (push them out)
    4. EDGE       on the blue tape                  -> forward is blocked, backward still works
    5. BOOST      opponent close + human charging   -> full power forward
    6. DRIVE      otherwise                         -> drive exactly how the levers say

Shared control / sensor fusion:
    EDGE_PUSH fuses the levers + the color sensor + the HC-SR04
                                                 (forward at the edge means pushing, not falling off)
    EDGE      fuses the levers + the color sensor   (the robot can refuse the human)
    BOOST     fuses the levers + the HC-SR04         (the robot helps the human)
"""
import math
from dataclasses import dataclass
from typing import Optional

# ---- Tuning --------------------------------------------------------------
LEVER_DEADBAND = 10      # lever % treated as "centered" (joysticks never rest at exactly 0)
CHARGE_THRESHOLD = 20    # both levers above this % = the human is driving forward
BOOST_DISTANCE_CM = 30   # opponent closer than this triggers BOOST
MIN_VALID_CM = 0.5       # ignore readings closer than this (0 / tiny values are glitches)
BOOST_SPEED = 100        # full power
STALE_AFTER_S = 0.3      # a distance reading older than this is ignored
TAPE_HOLD_S = 0.3        # keep blocking forward this long after the tape was last seen


@dataclass
class Inputs:
    left: float                   # left lever, -100..100 (forward is positive)
    right: float                  # right lever, -100..100
    button: bool                  # controller button currently pressed?
    on_tape: bool                 # color sensor sees the blue tape?
    color_ok: bool                # color sensor connected and reporting?
    distance_cm: Optional[float]  # latest HC-SR04 reading (None = nothing / no echo)
    distance_age_s: float         # seconds since that reading arrived (inf = never)


@dataclass
class Decision:
    left: int
    right: int
    branch: str                   # which branch of the tree won
    play_sad_song: bool = False   # True only on the tick we become OUT


def _clean(v: float) -> int:
    """Turn a lever reading into a safe wheel speed (NaN -> 0, deadband, clamp)."""
    if v is None or math.isnan(v):
        return 0
    v = max(-100, min(100, int(round(v))))
    return 0 if abs(v) < LEVER_DEADBAND else v


class SumoBrain:
    def __init__(self):
        self.out = False
        self._button_was_down = False
        self._tape_until = -math.inf

    def opponent_close(self, inp: Inputs) -> bool:
        return (inp.distance_cm is not None
                and inp.distance_age_s <= STALE_AFTER_S
                and MIN_VALID_CM <= inp.distance_cm <= BOOST_DISTANCE_CM)

    def tick(self, inp: Inputs, now: float) -> Decision:
        # Button press (not hold) toggles OUT; pressing again after a round resets it.
        pressed = inp.button and not self._button_was_down
        self._button_was_down = inp.button
        just_went_out = False
        if pressed:
            self.out = not self.out
            just_went_out = self.out

        # 1. OUT
        if self.out:
            return Decision(0, 0, "OUT", play_sad_song=just_went_out)

        # 2. NO_EDGE: never drive blind
        if not inp.color_ok:
            return Decision(0, 0, "NO_EDGE")

        left, right = _clean(inp.left), _clean(inp.right)

        # Edge state: on the tape now, or within TAPE_HOLD_S of last seeing it
        if inp.on_tape:
            self._tape_until = now + TAPE_HOLD_S
        at_edge = now < self._tape_until
        charging_at_opponent = (left > CHARGE_THRESHOLD and right > CHARGE_THRESHOLD
                                and self.opponent_close(inp))

        # 3. EDGE_PUSH: at the edge, but the opponent is right in front of us,
        #    so forward means pushing them, not driving out. Push at full power.
        if at_edge and charging_at_opponent:
            return Decision(BOOST_SPEED, BOOST_SPEED, "EDGE_PUSH")

        # 4. EDGE: at the edge with nothing in front: refuse to drive forward
        if at_edge:
            return Decision(min(left, 0), min(right, 0), "EDGE")

        # 5. BOOST: human is charging and the opponent is right there
        if charging_at_opponent:
            return Decision(BOOST_SPEED, BOOST_SPEED, "BOOST")

        # 6. DRIVE: human in control
        return Decision(left, right, "DRIVE")
