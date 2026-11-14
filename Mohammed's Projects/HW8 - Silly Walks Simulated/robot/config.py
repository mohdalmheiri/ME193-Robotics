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
ROBOT_RIGHT_IS_LEGO = "right"           # "right" or "left"
# Sign of the percent speed that turns each leg in the UPRIGHT-walking direction, per
# robot side (the other sign makes the robot flip over).  [calibration/motor_direction.py]
UPRIGHT_PERCENT_SIGN = {"right": +1, "left": +1}
# +1 if that motor's encoder degrees go UP when the leg turns in the simulator's +q
# direction, -1 if they go DOWN.                          [calibration/motor_direction.py]
ENCODER_SIGN = {"right": -1, "left": -1}
# Encoder absolute position (deg, 0..359) when the leg points straight forward
# (simulator q = 0).                                     [calibration/leg_zero.py]
LEG_ZERO_DEG = {"right": 0.0, "left": 0.0}
# Leg speed (rpm) at each percent command, measured.     [calibration/measure_rpm.py]
# PLACEHOLDER = a straight line through 120 rpm at 100 %, the policy's assumed top speed.
# If the measured rpm at 100 % is BELOW the policy's max (120 rpm), the policy can ask for
# speeds the motor cannot reach: run_policy warns loudly and the policy should be retrained
# with the real limit.
RPM_AT_PERCENT = [(0, 0.0), (25, 30.0), (50, 60.0), (75, 90.0), (100, 120.0)]
RPM_MEASURED = False        # set True after measure_rpm.py; run_policy warns while False
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
BODY_FROM_HUB = {"x": "+x", "y": "+y", "z": "+z"}
# The hub's pitch/roll/yaw numbers: unit (1 = degrees, 0.1 = tenths of a degree) and sign.
ANGLE_UNIT_DEG = 1.0                                      # [calibration/imu_axes.py]
PITCH_SIGN = +1       # +1: nose (front) UP reads positive  [calibration/imu_axes.py]
ROLL_SIGN = +1        # +1: RIGHT side DOWN reads positive  [calibration/imu_axes.py]
YAW_SIGN = +1         # +1: turning LEFT (counter-clockwise seen from above) reads positive
GYRO_SIGN = +1        # +1: right-hand rule about the hub axes (deg/s)
# True if the hub reports our "pitch" (front up/down) in its ROLL field and vice versa (its
# own axis naming depends on how the Double Motor sits in the robot). [calibration/imu_axes.py]
PITCH_ROLL_SWAPPED = False
# Where the policy's "tilt" input comes from:
#   "pitch_roll": the hub's own filtered pitch/roll (default; training's tilt is pure
#                 gravity, and the raw accelerometer also feels every bump of the gait)
#   "accel":      the raw accelerometer (fallback if pitch/roll conventions are odd)
TILT_SOURCE = "pitch_roll"
