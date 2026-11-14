"""
Deliberately mis-wired "true hubs" for FakeRobot(hub=...): every value calibration measures
differs from config.py's defaults (LEGO sides swapped, a motor reversed, encoders counting
differently, odd leg zeros, a slower or faster motor, the motion sensor turned or upside down,
angles in tenths of a degree, flipped signs, pitch/roll swapped).
Used by robot/tests/test_calibration.py, robot/tests/test_calibrate.py and
`robot/calibrate.py --fake --fake-hub <name>` (a rehearsal against a wrongly wired robot).
"""

FAKE_HUBS = {
    "turned-90": {           # sensor turned 90 deg
        "ROBOT_RIGHT_IS_LEGO": "left", "UPRIGHT_PERCENT_SIGN": {"right": -1, "left": +1},
        "ENCODER_SIGN": {"right": +1, "left": -1}, "LEG_ZERO_DEG": {"right": 200.0, "left": 37.0},
        "RPM_AT_PERCENT": [(0, 0.0), (100, 95.0)],
        "BODY_FROM_HUB": {"x": "-y", "y": "+x", "z": "+z"}, "ANGLE_UNIT_DEG": 0.1,
        "PITCH_SIGN": -1, "ROLL_SIGN": +1, "YAW_SIGN": -1, "GYRO_SIGN": -1, "PITCH_ROLL_SWAPPED": True},
    "upside-down": {         # sensor upside down
        "ROBOT_RIGHT_IS_LEGO": "right", "UPRIGHT_PERCENT_SIGN": {"right": -1, "left": -1},
        "ENCODER_SIGN": {"right": -1, "left": +1}, "LEG_ZERO_DEG": {"right": 355.0, "left": 90.0},
        "RPM_AT_PERCENT": [(0, 0.0), (100, 130.0)],
        "BODY_FROM_HUB": {"x": "+x", "y": "-y", "z": "-z"}, "ANGLE_UNIT_DEG": 1.0,
        "PITCH_SIGN": +1, "ROLL_SIGN": -1, "YAW_SIGN": +1, "GYRO_SIGN": +1, "PITCH_ROLL_SWAPPED": False},
}
