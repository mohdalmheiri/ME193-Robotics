"""
THE unit conversion: hub readings <-> the policy's numbers. (Units are the #1 sim-to-real
bug risk, so this is the only file that does it, and tests/test_units.py proves it matches
training.)

  hub reports (robot_interface.Reading)            policy saw in training (MJLab)
  -------------------------------------            -------------------------------------------
  pitch, roll  [deg or 0.1 deg, hub axes]    ->    tilt: unit gravity vector in body axes
  (or accelerometer, milli-g, +1000 "up")          ((0, 0, -1) when level; gravity points DOWN)
  gyroscope    [deg/s, hub axes]             ->    gyro: rad/s in body axes
  yaw          [deg or 0.1 deg, reset at start] -> heading: sin, cos of the heading change
                                                   (radians, counter-clockwise positive)
  motor absolutePosition [deg 0..359]        ->    leg angle q: rad, 0 = leg forward,
                                                   sin(qR), sin(qL), cos(qR), cos(qL)
  motor position [deg, counted] over time    ->    leg speed: rad/s / max speed (120 rpm)
  (laptop's own previous command)            ->    last command: -1..1 per leg

  policy output a (-1..1 per leg)            ->    percent speed for movement_move_tank
     rpm = 120 * (a + 1) / 2   (upright direction; -1 = stop, +1 = 120 rpm)
     percent = from the measured rpm-per-percent table (config.RPM_AT_PERCENT), clipped to
     100 (and REPORTED when clipped), rounded to a whole percent, given the upright sign.

Every robot-specific assumption (axis directions, signs, zero offsets, rpm table) comes
from config.py.
"""

import json
import math
from pathlib import Path

import numpy as np

import config as C

MODEL_DIR = Path(__file__).resolve().parent / "model"
META = json.loads((MODEL_DIR / "policy_meta.json").read_text())
MAX_RPM = META["max_speed_rpm"]                     # policy's full speed (120 rpm)
MAX_RAD_S = MAX_RPM * 2 * math.pi / 60
SIDES = ("right", "left")                           # policy order: right first, then left
OBS_SIZE = sum(n for _, n, _ in META["observation_layout"])     # 16


# ------------------------------------------------------------------ axes
def axis_map(body_from_hub: dict) -> np.ndarray:
    """A BODY_FROM_HUB setting as a 3x3 matrix M with body_vector = M @ hub_vector."""
    M = np.zeros((3, 3))
    for row, body_axis in enumerate("xyz"):
        spec = body_from_hub[body_axis]              # e.g. "+y" or "-x"
        M[row, "xyz".index(spec[1])] = 1.0 if spec[0] == "+" else -1.0
    return M


BODY_FROM_HUB = axis_map(C.BODY_FROM_HUB)
HUB_FROM_BODY = BODY_FROM_HUB.T                      # a signed permutation: inverse = transpose


def gravity_from_pitch_roll(pitch_rad: float, roll_rad: float) -> np.ndarray:
    """Unit gravity vector in the hub's axes, from pitch and roll.

    Convention (FakeRobot uses exactly the same one): the hub's orientation is
    yaw about z, then pitch about x (positive = front/+y UP), then roll about y
    (positive = right/+x side DOWN). Gravity (0, 0, -1) seen from the hub is then
        ( sin(roll) cos(pitch),  -sin(pitch),  -cos(roll) cos(pitch) ).
    Check: nose up -> gravity points toward the tail (-y); right side down -> +x.
    """
    return np.array([math.sin(roll_rad) * math.cos(pitch_rad),
                     -math.sin(pitch_rad),
                     -math.cos(roll_rad) * math.cos(pitch_rad)])


def pitch_roll_from_gravity(g_hub: np.ndarray):
    """Inverse of gravity_from_pitch_roll (for FakeRobot): unit gravity -> (pitch, roll) rad."""
    gx, gy, gz = g_hub / np.linalg.norm(g_hub)
    return math.asin(max(-1.0, min(1.0, -gy))), math.atan2(gx, -gz)


# ------------------------------------------------------------------ readings -> inputs
def tilt(reading) -> np.ndarray:
    """The policy's 'tilt' input: unit gravity direction in BODY axes."""
    if C.TILT_SOURCE == "pitch_roll":
        hub_p, hub_r = (reading.roll, reading.pitch) if C.PITCH_ROLL_SWAPPED else (reading.pitch, reading.roll)
        p = math.radians(C.PITCH_SIGN * hub_p * C.ANGLE_UNIT_DEG)
        r = math.radians(C.ROLL_SIGN * hub_r * C.ANGLE_UNIT_DEG)
        g_hub = gravity_from_pitch_roll(p, r)
    else:
        # An accelerometer at rest reads +1 g pointing UP (it feels the table pushing),
        # so gravity's direction is MINUS the reading. (Classic sign bug.)
        a = np.asarray(reading.accel_mg, dtype=float)
        g_hub = -a / max(np.linalg.norm(a), 1e-9)
    return BODY_FROM_HUB @ g_hub


def gyro(reading) -> np.ndarray:
    """deg/s in hub axes -> rad/s in body axes."""
    w_hub = C.GYRO_SIGN * np.radians(np.asarray(reading.gyro_dps, dtype=float))
    return BODY_FROM_HUB @ w_hub


def heading(reading) -> float:
    """Heading change since the start (rad, counter-clockwise from above positive)."""
    return math.radians(C.YAW_SIGN * reading.yaw * C.ANGLE_UNIT_DEG)


def leg_angle(reading, side: str) -> float:
    """Encoder absolute position -> simulator leg angle q (rad)."""
    deg = C.ENCODER_SIGN[side] * (reading.motors[side].absolute_deg - C.LEG_ZERO_DEG[side])
    return math.radians(deg)


class LegSpeed:
    """The policy's leg speed input (rad/s, simulator sign: upright walking is NEGATIVE).

    config.LEG_SPEED_SOURCE chooses how:
      "encoder":   ENCODER_SIGN * (position now - position before) / (time now - time before),
                   the average speed over the last decision. If no new sensor message
                   arrived since the last decision, the previous estimate is kept.
      "hub_speed": the hub's speed report in percent -> rpm through the rpm table ->
                   rad/s; a positive percent in the UPRIGHT direction is a negative
                   simulator speed.
    """

    def __init__(self):
        self.prev = None                 # (t, {side: position_deg})
        self.value = {s: 0.0 for s in SIDES}   # rad/s, simulator sign

    def update(self, reading) -> dict:
        if C.LEG_SPEED_SOURCE == "hub_speed":
            for s in SIDES:
                pct = reading.motors[s].speed_pct * C.UPRIGHT_PERCENT_SIGN[s]   # + = upright
                rpm = percent_to_rpm(pct) if pct >= 0 else -percent_to_rpm(-pct)
                self.value[s] = -rpm * 2 * math.pi / 60
            return self.value
        now = (reading.t, {s: reading.motors[s].position_deg for s in SIDES})
        if self.prev is not None and now[0] > self.prev[0]:
            dt = now[0] - self.prev[0]
            for s in SIDES:
                self.value[s] = math.radians(C.ENCODER_SIGN[s] * (now[1][s] - self.prev[1][s])) / dt
        if self.prev is None or now[0] > self.prev[0]:
            self.prev = now
        return self.value


def observation(reading, leg_speed: dict, last_command: np.ndarray) -> np.ndarray:
    """All 16 policy inputs, in the exact training order (policy_meta.json)."""
    h = heading(reading)
    q = [leg_angle(reading, s) for s in SIDES]
    return np.concatenate([
        tilt(reading),                                        # 3
        gyro(reading),                                        # 3
        [math.sin(h), math.cos(h)],                           # 2
        [math.sin(q[0]), math.sin(q[1]), math.cos(q[0]), math.cos(q[1])],   # 4
        [leg_speed[s] / MAX_RAD_S for s in SIDES],            # 2
        np.clip(last_command, -1.0, 1.0),                     # 2
    ]).astype(np.float32)


# ------------------------------------------------------------------ outputs -> percent
_PCT = np.array([p for p, _ in C.RPM_AT_PERCENT], dtype=float)
_RPM = np.array([r for _, r in C.RPM_AT_PERCENT], dtype=float)
RPM_AT_100 = float(np.interp(100.0, _PCT, _RPM))


def rpm_to_percent(rpm: float) -> float:
    """Percent needed for an upright leg speed (rpm), from the measured table. Above the
    table's top speed it extrapolates linearly (the caller clips at 100 %)."""
    if rpm <= _RPM[-1]:
        return float(np.interp(rpm, _RPM, _PCT))
    return 100.0 * rpm / RPM_AT_100


def percent_to_rpm(pct: float) -> float:
    """Leg speed (rpm) for a percent: the motor's speed at a percent command, or the speed a
    percent REPORT stands for. Above the table's top it extrapolates linearly (a leg can be
    pushed faster than its motor drives it, e.g. when the body vaults over it)."""
    p = abs(pct)
    if p <= _PCT[-1]:
        return float(np.interp(p, _PCT, _RPM))
    return RPM_AT_100 * p / 100.0


def command(action: np.ndarray):
    """Policy action (right, left) -> whole percents for each ROBOT side, plus a report.

    Returns (percent dict, info dict). info["clipped"] lists the sides whose wanted speed
    was above 100 % (the motor's top speed), with the wanted percent.
    """
    a = np.clip(np.asarray(action, dtype=float), -1.0, 1.0)
    pct, info = {}, {"wanted_rpm": {}, "clipped": {}}
    for i, s in enumerate(SIDES):
        rpm = MAX_RPM * (a[i] + 1.0) / 2.0
        p = rpm_to_percent(rpm)
        info["wanted_rpm"][s] = rpm
        if p > 100.0 + 1e-9:
            info["clipped"][s] = p
            p = 100.0
        pct[s] = int(round(p)) * C.UPRIGHT_PERCENT_SIGN[s]
    return pct, info


def action_for_percent(pct: float) -> float:
    """Inverse of command(): the action (-1..1) that gives this percent (for baselines)."""
    rpm = percent_to_rpm(pct)
    return float(np.clip(2 * rpm / MAX_RPM - 1, -1, 1))


def speed_limit_warning():
    """Text warning if the motor can't reach the policy's top speed, else None."""
    if RPM_AT_100 < 0.97 * MAX_RPM:                     # 3 % allowance for measurement rounding
        return (f"WARNING: the motor reaches only {RPM_AT_100:.0f} rpm at 100 %, but the policy "
                f"was trained for up to {MAX_RPM:.0f} rpm. Commands above {RPM_AT_100:.0f} rpm "
                "will be clipped, so the robot cannot do everything the policy learned. "
                "Retrain with MAX_SPEED_RPM set to the measured limit.")
    return None
