"""
Builds the full simulation (robot + table + motors) on top of the raw CAD export.

Why this file exists:
  cad/robot.xml comes straight from onshape-to-robot and is never edited by hand,
  so re-exporting after a CAD change can't wipe out our work. But the raw export
  isn't ready for physics:
    1. The body is "fixed" in the Onshape assembly, so the export bolts it to the
       world (there is no free joint), and the robot would hang in mid-air.
    2. Collisions were switched off in the export (only detailed meshes for looks).
    3. There are no motors.
    4. There is no table.
  This script loads robot.xml with MuJoCo's model-editing API (MjSpec), adds
  those four things, and compiles the result into a ready-to-run model.

How the pieces are added:
  - Free joint: added to the "body" link, so the whole robot can slide, tip and
    fall under gravity (6 degrees of freedom), with the legs hinged on top.
  - Collision shapes: a box for the body, a cylinder for each motor hub, and a
    box for each leg. They live in group 3 (hidden by default in the viewer),
    while the CAD meshes stay visible but don't collide (contype=0). Simple shapes
    make contact clean: a box face on a flat floor gives steady contact points,
    while a triangle mesh gives many small, jumpy contacts.
    Leg boxes are measured from each leg's mesh (its bounding box in the leg's
    own frame), so they always match the CAD. The body has hubs sticking out,
    so its box and cylinders come from the sizes in settings.py instead.
  - Motors: one velocity actuator per leg joint (see settings.py).
  - Table: an infinite flat plane at Z = 0, with 10 cm checker squares for
    judging distance. The robot is lifted so the body's bottom (15 mm below the
    axle) starts DROP_HEIGHT above it.

Usage:
  from build_scene import build_model     # used by the other sim scripts
  python sim/build_scene.py               # just rebuild and save sim/scene.xml

Each build also writes sim/scene.xml, a plain MuJoCo file you can open in any
MuJoCo viewer (or later in MJLab) without Python.
"""

from pathlib import Path

import mujoco
import numpy as np

import settings as S

SIM_DIR = Path(__file__).resolve().parent
ROBOT_XML = SIM_DIR.parent / "cad" / "robot.xml"
SCENE_XML = SIM_DIR / "scene.xml"

LEG_BODIES = {"right": "leg_right", "left": "leg_left"}   # joint name -> link name

# Rotates a cylinder's axis from MuJoCo's default (along Z) to along X:
# a 90 degree turn about Y, written as a quaternion (w, x, y, z).
Z_TO_X = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]


def _leg_box_from_mesh(spec):
    """Measure each leg mesh's bounding box in its own leg frame.

    Compiles the raw export once, then for each leg's mesh geom moves every mesh
    vertex into the leg body's frame (vertex rotated by the geom's orientation,
    plus the geom's position) and takes the min and max along each axis.
    Returns {link_name: (center, half_sizes)}.
    """
    model = spec.copy().compile()
    boxes = {}
    for link in LEG_BODIES.values():
        body_id = model.body(link).id
        geom_id = next(g for g in range(model.ngeom) if model.geom_bodyid[g] == body_id)
        mesh_id = model.geom_dataid[geom_id]
        start, count = model.mesh_vertadr[mesh_id], model.mesh_vertnum[mesh_id]
        verts = model.mesh_vert[start:start + count]
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, model.geom_quat[geom_id])
        in_body = verts @ rot.reshape(3, 3).T + model.geom_pos[geom_id]
        lo, hi = in_body.min(axis=0), in_body.max(axis=0)
        boxes[link] = ((lo + hi) / 2, (hi - lo) / 2)
    return boxes


def _add_collision_geom(body, **kwargs):
    """Add a simple collision shape: hidden group 3, colliding, with our friction.

    solref = [time constant, damping ratio] sets how stiff the contact is
    (see CONTACT_TIMECONST in settings.py); damping ratio 1 = no bounce.
    """
    geom = body.add_geom(group=3, contype=1, conaffinity=1,
                         friction=[S.FRICTION, 0.005, 0.0001],
                         solref=[S.CONTACT_TIMECONST, 1.0],
                         rgba=[1, 0.4, 0.1, 0.5], **kwargs)
    return geom


def build_spec():
    """Return an MjSpec of the complete scene (not compiled yet)."""
    spec = mujoco.MjSpec.from_file(str(ROBOT_XML))

    # ----- physics options
    spec.option.timestep = S.TIMESTEP
    # "implicitfast" treats velocity-dependent forces (our velocity motors)
    # implicitly, which stays stable even with a stiff speed controller.
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.option.gravity = [0, 0, -9.81]
    if S.CONTACT_TIMECONST < 2 * S.TIMESTEP:
        raise ValueError("settings: CONTACT_TIMECONST must be at least 2 x TIMESTEP")

    # ----- 1. free joint + starting height
    body = spec.body("body")
    body.add_freejoint(name="free")
    body.pos = [0, 0, S.TABLE_HEIGHT_BELOW_AXLE + S.DROP_HEIGHT]

    # ----- 2. collision shapes
    sx, sy, sz = S.BODY_SIZE
    _add_collision_geom(body, name="body_box", type=mujoco.mjtGeom.mjGEOM_BOX,
                        size=[sx / 2, sy / 2, sz / 2], pos=list(S.BODY_CENTER))
    hub_x = sx / 2 + S.HUB_LENGTH / 2              # centre of each hub cylinder
    for side, sign in (("right", 1), ("left", -1)):
        _add_collision_geom(body, name=f"hub_{side}", type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                            size=[S.HUB_RADIUS, S.HUB_LENGTH / 2, 0],
                            pos=[sign * hub_x, 0, 0], quat=Z_TO_X)
    for link, (center, half) in _leg_box_from_mesh(spec).items():
        _add_collision_geom(spec.body(link), name=f"{link}_box",
                            type=mujoco.mjtGeom.mjGEOM_BOX,
                            size=half.tolist(), pos=center.tolist())

    # ----- 3. joint properties + velocity motors
    for joint_name in LEG_BODIES:
        joint = spec.joint(joint_name)
        joint.frictionloss = S.JOINT_FRICTION
        joint.armature = S.JOINT_ARMATURE
        motor = spec.add_actuator(name=f"motor_{joint_name}", target=joint_name,
                                  trntype=mujoco.mjtTrn.mjTRN_JOINT)
        motor.set_to_velocity(kv=S.MOTOR_KV)
        motor.forcelimited = mujoco.mjtLimited.mjLIMITED_TRUE
        motor.forcerange = [-S.MOTOR_MAX_TORQUE, S.MOTOR_MAX_TORQUE]

    # ----- 4. table, light and looks
    spec.add_texture(name="grid", type=mujoco.mjtTexture.mjTEXTURE_2D,
                     builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER, width=300, height=300,
                     rgb1=[0.82, 0.72, 0.58], rgb2=[0.72, 0.62, 0.48],
                     mark=mujoco.mjtMark.mjMARK_EDGE, markrgb=[0.4, 0.35, 0.3])
    table_mat = spec.add_material(name="table", texuniform=True, texrepeat=[10, 10])
    table_mat.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "grid"  # 10 squares per metre
    spec.worldbody.add_geom(name="table", type=mujoco.mjtGeom.mjGEOM_PLANE,
                            size=[0, 0, 0.05], material="table",
                            friction=[S.FRICTION, 0.005, 0.0001],
                            solref=[S.CONTACT_TIMECONST, 1.0])
    spec.worldbody.add_light(pos=[0, 0, 1.5], dir=[0, 0, -1],
                             type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
    # Small robot: zoom the default camera in and look at the robot.
    spec.stat.extent = 0.25
    spec.stat.center = [0, -0.02, 0.02]
    # Off-screen image buffer (default 640x480) big enough for 1280x720 videos.
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 720
    return spec


def save_scene_xml(spec):
    """Write sim/scene.xml with mesh paths relative to sim/ (no personal paths)."""
    out = spec.copy()
    out.meshdir = "../cad/assets"
    SCENE_XML.write_text(out.to_xml())


def build_model():
    """Build, save sim/scene.xml, and return the compiled MjModel."""
    spec = build_spec()
    model = spec.compile()
    save_scene_xml(spec)
    return model


def settle(model, data, seconds=1.0):
    """Let the robot sit with motors commanded to zero speed for a while."""
    data.ctrl[:] = 0.0
    for _ in range(int(seconds / model.opt.timestep)):
        mujoco.mj_step(model, data)


if __name__ == "__main__":
    m = build_model()
    print(f"Built {SCENE_XML.relative_to(SIM_DIR.parent)}: {m.nbody} bodies, "
          f"{m.njnt} joints, {m.ngeom} geoms, {m.nu} motors")
