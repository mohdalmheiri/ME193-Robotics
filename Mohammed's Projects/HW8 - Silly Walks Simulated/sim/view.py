"""
Opens the robot in MuJoCo's interactive 3D viewer with both motors running.

How it works:
  - Builds the scene from settings.py (same model the tests use).
  - Registers a "control callback": a small function MuJoCo calls before every
    physics step. It sets both motor commands to the chosen speed, so the legs
    keep spinning even after you reset the simulation in the viewer.
  - Starts the viewer, which runs the physics in real time and draws it.

Viewer tips:
  - Space: pause/resume.   Backspace: reset to the start.
  - Key 3: show/hide the simple collision shapes (orange, geom group 3).
    Key 2: show/hide the detailed CAD meshes.
  - Double-click the robot, then Ctrl + right-drag to push it around.

Run:  python sim/view.py              (speed from settings.py)
      python sim/view.py --rpm -60    (any speed; 0 = motors hold still)
"""

import argparse
import math

import mujoco
import mujoco.viewer

import settings as S
from build_scene import build_model

parser = argparse.ArgumentParser(description="Interactive MuJoCo viewer")
parser.add_argument("--rpm", type=float, default=S.MOTOR_SPEED_RPM, help="motor speed (both legs)")
args = parser.parse_args()
speed = args.rpm * 2 * math.pi / 60


def control(model, data):
    data.ctrl[:] = speed       # same speed on both legs, every physics step


model = build_model()
mujoco.set_mjcb_control(control)
mujoco.viewer.launch(model)    # blocks until the window is closed
