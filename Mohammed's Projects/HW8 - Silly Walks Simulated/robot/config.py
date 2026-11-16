"""
Everything about the REAL robot that the software has to assume until it is measured.

Each value has a default (our best guess) and the calibration script that measures it
(robot/calibration/...). After a calibration run, copy the printed value here. Both
RealRobot and FakeRobot read this file: FakeRobot pretends to be a hub that behaves exactly
as described here, so if a value turns out wrong on the real robot, fixing it here fixes the
conversion for the real robot too (and FakeRobot keeps agreeing with it).

Coordinate words used below
  Robot body axes (the simulator's):  x = robot's RIGHT, y = robot's FRONT (walking
  direction), z = UP. Leg angle q = 0 when the leg points straight forward (horizontal);
  in the simulator, walking upright turns both legs in the NEGATIVE q direction.
  "LEGO left/right" means the Double Motor's own naming (le.MOTOR_LEFT / le.MOTOR_RIGHT,
  and the two arguments of movement_move_tank(left, right)).
"""

# ------------------------------------------------------------------ connection / timing
NOTIFICATION_MS = 20        # we ASK the hub for a sensor message every 20 ms; MT1 measured
                            # one every ~31 ms in practice. FakeRobot uses 31 ms.
STALE_SENSOR_S = 0.30       # safety: stop if no new sensor message arrives for this long
MAX_RUN_S = 30.0            # safety: default time limit of one run (run_policy --seconds)

# ------------------------------------------------------------------ motors
# Which LEGO side drives the robot's RIGHT leg.        [calibration/motor_direction.py]
# measured by calibrate.py on 2026-11-16 12:27 (was: "right")
ROBOT_RIGHT_IS_LEGO = "right"           # "right" or "left"
# Sign of the percent speed that turns each leg in the UPRIGHT-walking direction, per
# robot side (the other sign makes the robot flip over).  [calibration/motor_direction.py]
# measured by calibrate.py on 2026-11-16 12:27 (was: {"right": +1, "left": +1})
UPRIGHT_PERCENT_SIGN = {"right": +1, "left": +1}
# +1 if that motor's encoder degrees go UP when the leg turns in the simulator's +q
# direction, -1 if they go DOWN.                          [calibration/motor_direction.py]
# measured by calibrate.py on 2026-11-16 12:27 (was: {"right": -1, "left": -1})
ENCODER_SIGN = {"right": -1, "left": +1}
# Encoder absolute position (deg, 0..359) when the leg points straight forward
# (simulator q = 0).                                     [calibration/leg_zero.py]
# measured by calibrate.py on 2026-11-16 12:39 (was: {"right": 355.0, "left": 173.0})
LEG_ZERO_DEG = {"right": 0.0, "left": 177.1}
# Leg speed (rpm) at each percent command, measured.     [calibration/measure_rpm.py]
# MEASURED on the real robot (Julian, 2026-11-16, robot on the stand, legs free): 165.8 rpm
# at 100 %, about HALF the published 322-346 rpm no-load spec (the placeholder used 334).
# Under load (walking) it may be lower; not measured yet (checklist step O1).
# measured by calibrate.py on 2026-11-16 12:39 (was: [(0, 0.0), (25, 41.7), (50, 82.8), (75, 124.4), (100, 167.6)])
RPM_AT_PERCENT = [(0, 0.0), (25, 41.4), (50, 83.7), (75, 124.7), (100, 165.8)]
# measured by calibrate.py on 2026-11-16 12:39 (was: True)
RPM_MEASURED = True        # set True after measure_rpm.py; run_policy warns while False
# The policy's top leg speed on THIS robot (rpm). v2 policies output a FRACTION of the top
# speed: leg speed = POLICY_TOP_RPM * (a + 1) / 2. Training drew each robot's top speed from
# 80-140 rpm (policy_meta.json "top_speed_rpm_range"), so this must lie inside that range;
# units.py refuses anything else. The real motor reaches 165.8 rpm at 100 % (measured
# 2026-11-16), so a full action is 66 % power: the legs never go faster than in training.
# 110 = the middle of the trained range.
POLICY_TOP_RPM = 110.0

# The motor's published specs (Julian, 2026-11-14; source still to be confirmed), at 4.2 V
# (full battery). Used ONLY by FakeRobot's "spec motor" robustness tests, never by the
# real-robot path.  Motor weight 80 g (merlinsbricks.com set database; may include packaging).
# !! CONTRADICTED BY OUR MEASUREMENT: our motor reaches 165.8 rpm at 100 % (measure_rpm.py on
# the stand, Julian, 2026-11-16; RPM_AT_PERCENT above), about HALF the published 322-346 rpm.
# These numbers are kept ONLY for the spec-motor robustness tests (robot/check_spec_motor.py,
# sim_hand_tests.py --motor regulated/pwm, test_units.py 3b): read those as a "what if the
# motor were faster (~334 rpm)?" check, NOT as a model of our real motor. Our real motor is
# described by RPM_AT_PERCENT.
MOTOR_SPEC = {
    "no_load_rpm": (322.0, 346.0),
    "rpm_at_50_mNm": (192.0, 220.0),
    "stall_torque_Nm": (0.148, 0.173),
    "weight_kg": 0.080,
}
# Where the policy's "leg speed" input comes from:
#   "encoder":   how far the counted encoder position moved over the last 0.05 s (what
#                certainly happened; but SMOOTHER than training, which used the simulator's
#                instantaneous, very spiky joint speed - see docs/process_log.md)
#   "hub_speed": the hub's own speed report (percent -> rpm via the table above). Closest to
#                training IF the hub reports the actual instantaneous speed; its filtering
#                is unknown until calibration/measure_rpm.py compares the two.
LEG_SPEED_SOURCE = "encoder"

# ------------------------------------------------------------------ motion sensor (IMU)
# How the hub's sensor axes line up with the robot body axes: for each BODY axis, which
# hub axis (and sign) points the same way.                 [calibration/imu_axes.py]
# Default: the hub lies flat (MT1: z reads +1000 milli-g when flat), its +y to the front.
# measured by calibrate.py on 2026-11-16 12:39 (was: {"x": "-y", "y": "+x", "z": "+z"})
BODY_FROM_HUB = {"x": "-y", "y": "+x", "z": "+z"}
# The hub's pitch/roll/yaw numbers: unit (1 = degrees, 0.1 = tenths of a degree) and sign.
# measured by calibrate.py on 2026-11-16 12:39 (was: 0.1)
ANGLE_UNIT_DEG = 0.1                                      # [calibration/imu_axes.py]
# measured by calibrate.py on 2026-11-16 12:39 (was: +1)
PITCH_SIGN = +1       # +1: nose (front) UP reads positive  [calibration/imu_axes.py]
# measured by calibrate.py on 2026-11-16 12:39 (was: +1)
ROLL_SIGN = +1        # +1: RIGHT side DOWN reads positive  [calibration/imu_axes.py]
# measured by calibrate.py on 2026-11-16 12:39 (was: +1)
YAW_SIGN = +1         # +1: turning LEFT (counter-clockwise seen from above) reads positive
# measured by calibrate.py on 2026-11-16 12:39 (was: +1)
GYRO_SIGN = +1        # +1: right-hand rule about the hub axes (deg/s)
# True if the hub reports our "pitch" (front up/down) in its ROLL field and vice versa (its
# own axis naming depends on how the Double Motor sits in the robot). [calibration/imu_axes.py]
# measured by calibrate.py on 2026-11-16 12:39 (was: True)
PITCH_ROLL_SWAPPED = True
# Where the policy's "tilt" input comes from:
#   "pitch_roll": the hub's own filtered pitch/roll (default; training's tilt is pure
#                 gravity, and the raw accelerometer also feels every bump of the gait)
#   "accel":      the raw accelerometer (fallback if pitch/roll conventions are odd)
TILT_SOURCE = "pitch_roll"
