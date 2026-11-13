"""
The HW8 robot prepared for MJLab: the CAD export + free joint + simple collision shapes.

Why this is separate from sim/build_scene.py:
  - MJLab runs in its own environment (.venv-mjlab, MuJoCo 3.11), while sim/ uses
    MuJoCo 4.0 in the shared .venv. The sim/ scripts are left untouched.
  - MJLab builds the floor, the motors and the physics options itself, so here we
    only describe the robot. Motors are configured in the task files (walk_straight_task.py, speedtest_task.py).
The collision shapes use the same method and sizes as sim/build_scene.py (it
imports sim/settings.py for the numbers), so both models describe the same robot.

How it works:
  1. Load cad/robot.xml (straight from onshape-to-robot) into an MjSpec.
  2. Add a free joint to the body (the Onshape assembly fixes the body, so the export
     has none; MJLab treats a robot without one as bolted to the world).
  3. Add a box for the body, a cylinder per motor hub, and a box per leg (measured
     from the leg mesh). The CAD meshes stay for looks only.
  4. Give these shapes contact priority 1. When two touching shapes disagree on
     contact settings, MuJoCo normally averages them; MJLab's floor keeps the soft
     default (0.02 s), which would dilute our stiffer setting. With higher priority,
     our shapes' friction and stiffness are used instead.
"""

import sys
from pathlib import Path

import mujoco
import numpy as np

HW8 = Path(__file__).resolve().parent.parent
ROBOT_XML = HW8 / "cad" / "robot.xml"
sys.path.insert(0, str(HW8 / "sim"))
import settings as S  # noqa: E402  (only plain numbers; no MuJoCo-version-specific code)

LEGS = ("leg_right", "leg_left")
Z_TO_X = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]   # cylinder axis Z -> X


def _leg_boxes(spec):
    """Bounding box of each leg mesh in its own body frame -> (center, half_size)."""
    model = spec.copy().compile()
    boxes = {}
    for link in LEGS:
        b = model.body(link).id
        g = next(i for i in range(model.ngeom) if model.geom_bodyid[i] == b)
        mid = model.geom_dataid[g]
        verts = model.mesh_vert[model.mesh_vertadr[mid]:][:model.mesh_vertnum[mid]]
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, model.geom_quat[g])
        pts = verts @ rot.reshape(3, 3).T + model.geom_pos[g]
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        boxes[link] = ((lo + hi) / 2, (hi - lo) / 2)
    return boxes


def leg_box_extent():
    """Leg box corners in leg coordinates, for placing the robot above the table.

    Returns (along_lo, along_hi, across_lo, across_hi) in metres: "along" runs down the
    leg from the axle (the long arm is positive), "across" is the leg's height. At leg
    angle 0 the leg points to the front (+Y) and "across" is vertical. After turning the
    leg by angle q around the axle, a point (along, across) is at height
    along*sin(q) + across*cos(q) relative to the axle.
    """
    center, half = _leg_boxes(mujoco.MjSpec.from_file(str(ROBOT_XML)))["leg_right"]
    # Leg frame axes (from the export): x = along the leg, y = across (vertical at q=0),
    # z = along the axle.
    return (center[0] - half[0], center[0] + half[0], center[1] - half[1], center[1] + half[1])


def make_robot_spec(contact_timeconst: float) -> mujoco.MjSpec:
    """Return the robot as an MjSpec, with contact stiffness `contact_timeconst` (s)."""
    spec = mujoco.MjSpec.from_file(str(ROBOT_XML))
    leg_boxes = _leg_boxes(spec)
    body = spec.body("body")
    body.add_freejoint(name="free")

    def collide(parent, **kw):
        parent.add_geom(group=3, contype=1, conaffinity=1, priority=1,
                        friction=[S.FRICTION, 0.005, 0.0001],
                        solref=[contact_timeconst, 1.0], **kw)

    sx, sy, sz = S.BODY_SIZE
    collide(body, name="body_box", type=mujoco.mjtGeom.mjGEOM_BOX,
            size=[sx / 2, sy / 2, sz / 2], pos=list(S.BODY_CENTER))
    for side, sign in (("right", 1), ("left", -1)):
        collide(body, name=f"hub_{side}", type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                size=[S.HUB_RADIUS, S.HUB_LENGTH / 2, 0],
                pos=[sign * (sx / 2 + S.HUB_LENGTH / 2), 0, 0], quat=Z_TO_X)
    for link, (center, half) in leg_boxes.items():
        collide(spec.body(link), name=f"{link}_box", type=mujoco.mjtGeom.mjGEOM_BOX,
                size=half.tolist(), pos=center.tolist())
    return spec
