"""
Every number you might want to change for the HW8 simulation, in one place.

The other scripts import this file, so a change here takes effect the next time
you run any of them (sim/scene.xml is rebuilt automatically each run).

Units are SI: metres, kilograms, seconds, radians, newton-metres.
Values marked GUESS have not been measured on the real robot yet.
"""

import math

# --------------------------------------------------------------------------
# Motor speed: the main "knob". Not measured yet (GUESS).
# Both legs are commanded this speed. Positive = the right-hand rule around
# +X (the robot's right): leg tips that start pointing to the front (+Y)
# swing UP first, then back over the top, then down and forward along the table.
MOTOR_SPEED_RPM = 60.0                                  # revolutions per minute
MOTOR_SPEED = MOTOR_SPEED_RPM * 2 * math.pi / 60.0      # converted to rad/s

# --------------------------------------------------------------------------
# Motor model. MuJoCo's "velocity" actuator works like a cruise control:
#   torque = MOTOR_KV * (commanded speed - actual speed)
# then clipped to +/- MOTOR_MAX_TORQUE. A big KV holds speed tightly; the torque
# limit is what stops the motor from being unrealistically strong.
MOTOR_KV = 0.05            # N*m per (rad/s) of speed error (GUESS: holds speed within a few %)
MOTOR_MAX_TORQUE = 0.10    # N*m (GUESS: same order as LEGO's medium motors' stall torque)

# Joint properties. onshape-to-robot's defaults (frictionloss 0.1, armature 0.005)
# are sized for much bigger robots; 0.1 N*m of friction would eat the whole motor
# torque. These replace them.
JOINT_FRICTION = 0.002     # N*m of dry friction in the gearbox (GUESS)
JOINT_ARMATURE = 1e-5      # kg*m^2 extra inertia from the spinning motor rotor seen
                           # through the gears (GUESS; the leg itself is ~1e-6)

# --------------------------------------------------------------------------
# Simple collision shapes for the body (in metres, CAD frame: origin at the
# axle centre, +X right, +Y front, +Z up). From counting studs; check_model.py
# compares them against the real CAD mesh. The legs' boxes are measured
# automatically from their meshes, so they have no settings here.
BODY_SIZE = (0.048, 0.080, 0.030)        # box width (X), length (Y), height (Z)
BODY_CENTER = (0.0, -0.025, 0.0)         # box centre: axle is 15 mm from the front end
HUB_RADIUS = 0.0125                      # motor hubs: 25 mm diameter cylinders...
HUB_LENGTH = 0.008                       # ...sticking out 8 mm on each side

# --------------------------------------------------------------------------
# Contact and world.
FRICTION = 0.6             # sliding friction LEGO plastic vs table (GUESS, ABS on wood ~0.4-0.7)
TABLE_HEIGHT_BELOW_AXLE = 0.015   # table is at Z = -15 mm in the CAD frame
DROP_HEIGHT = 0.002        # start 2 mm above the table and let it settle

# Contact stiffness. MuJoCo pushes overlapping shapes apart over roughly this
# time. Its default (0.02 s) is too soft for a 100 g robot whose motors drive
# the legs into the table: the legs sank 5-10 mm (they are only 9.6 mm tall)
# and the walking distance came out ~40 % too long. 0.002 s keeps sinking
# under 1 mm. It must stay at least 2x TIMESTEP or the contact goes unstable.
CONTACT_TIMECONST = 0.002  # seconds
TIMESTEP = 0.0005          # physics step, seconds (2000 steps per simulated second)
