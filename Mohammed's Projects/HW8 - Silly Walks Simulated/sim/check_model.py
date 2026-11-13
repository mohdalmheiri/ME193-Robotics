"""
Checks that the MuJoCo model matches the real robot, and prints a PASS/WARN report.

What it checks and how:
  1. Masses: reads each link's mass from the compiled model and compares it with
     the expected value (body 100 g estimate, legs 2.85 g from the FeatureScript
     materials).
  2. Joints: after mj_forward (which places every body in the world), reads each
     hinge's world anchor point and axis. Both axes should be +/-X. The anchor
     should be on the axle line (y = z = 0). Its x position is reported, but a
     hinge's anchor can slide along its own axis without changing the physics,
     so only the distance from the axle line is pass/fail.
  3. Collision shapes vs CAD: for each link, compares the bounding box of the
     simple collision shapes with the bounding box of the detailed CAD mesh.
     They should agree to within 0.5 mm.
  4. Resting on the table: drops the robot from 2 mm and simulates 2 s with the
     motors holding still. Then checks the axle sits 15 mm above the table, the
     deepest contact overlap is tiny, the robot has stopped moving, and MuJoCo
     raised no instability warnings.

Run:  python sim/check_model.py
"""

import mujoco
import numpy as np

import settings as S
from build_scene import build_model, settle

EXPECTED_MASS_G = {"body": 100.0, "leg_right": 2.85, "leg_left": 2.85}
results = []   # (PASS/WARN, message), printed together at the end


def check(ok, message):
    results.append(("PASS" if ok else "WARN", message))


def world_bbox(model, data, geom_ids):
    """Axis-aligned world bounding box (min, max) of a set of geoms.

    Meshes: transform every vertex into the world. Boxes/cylinders: transform the
    8 corners of the shape's own bounding box (exact for boxes; for a cylinder
    lying along an axis, also exact for the box around it).
    """
    pts = []
    for g in geom_ids:
        rot = data.geom_xmat[g].reshape(3, 3)
        if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
            mid = model.geom_dataid[g]
            local = model.mesh_vert[model.mesh_vertadr[mid]:][:model.mesh_vertnum[mid]]
        else:
            s = model.geom_size[g]
            half = s if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX else [s[0], s[0], s[1]]
            local = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]) * half
        pts.append(local @ rot.T + data.geom_xpos[g])
    pts = np.vstack(pts)
    return pts.min(axis=0), pts.max(axis=0)


model = build_model()
data = mujoco.MjData(model)
mujoco.mj_forward(model, data)

# ---------------------------------------------------------------- 1. masses
print("MASSES")
for link, expected in EXPECTED_MASS_G.items():
    grams = model.body(link).mass[0] * 1000
    print(f"  {link:10} {grams:8.3f} g   (expected ~{expected} g)")
    check(abs(grams - expected) / expected < 0.02, f"mass of {link} = {grams:.3f} g")
total = sum(model.body(l).mass[0] for l in EXPECTED_MASS_G) * 1000
print(f"  total      {total:8.3f} g")

# ---------------------------------------------------------------- 2. joints
print("\nJOINTS (world frame, mm; table top is z = 0, so the axle starts 17 mm up)")
axle_height = data.xpos[model.body("body").id][2]   # body frame origin = axle centre
for name in ("right", "left"):
    j = model.joint(name).id
    anchor = data.xanchor[j] * 1000
    axis = data.xaxis[j]
    off_line = np.hypot(anchor[1], anchor[2] - axle_height * 1000)
    print(f"  {name:6} anchor = ({anchor[0]:6.1f}, {anchor[1]:5.1f}, {anchor[2]:5.1f})  "
          f"axis = ({axis[0]:+.3f}, {axis[1]:+.3f}, {axis[2]:+.3f})  "
          f"distance from axle line = {off_line:.3f} mm")
    check(abs(abs(axis[0]) - 1) < 1e-6, f"joint {name} axis is along X ({axis.round(3)})")
    check(off_line < 0.1, f"joint {name} lies on the axle line")
    if abs(abs(anchor[0]) - 32.0) > 0.1:
        print(f"         note: anchor x is {anchor[0]:+.1f} mm, not +/-32 mm. That is only a "
              f"shift ALONG the axle (mate connector on the other face of the leg), "
              f"which doesn't change how the hinge moves.")

# ------------------------------------------------------- 3. collision vs CAD
print("\nCOLLISION SHAPES vs CAD MESH (world bounding boxes, mm)")
for link in EXPECTED_MASS_G:
    b = model.body(link).id
    geoms = [g for g in range(model.ngeom) if model.geom_bodyid[g] == b]
    mesh = [g for g in geoms if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH]
    prim = [g for g in geoms if model.geom_contype[g] and g not in mesh]
    (mlo, mhi), (plo, phi) = world_bbox(model, data, mesh), world_bbox(model, data, prim)
    err = max(np.abs(mlo - plo).max(), np.abs(mhi - phi).max()) * 1000
    names = ", ".join(model.geom(g).name for g in prim)
    print(f"  {link:10} mesh  min {np.round(mlo*1000,1)}  max {np.round(mhi*1000,1)}")
    print(f"  {'':10} shape min {np.round(plo*1000,1)}  max {np.round(phi*1000,1)}  [{names}]")
    check(err < 0.5, f"{link} collision shapes match the CAD mesh to {err:.2f} mm")

# The hubs sit inside the body box's height range, so the bounding-box check
# above can't see a wrong hub radius. Check it directly: every CAD vertex outside
# the main box (|x| > half the box width) belongs to a hub, so its distance from
# the axle line should be at most HUB_RADIUS.
g = next(g for g in range(model.ngeom) if model.geom_bodyid[g] == model.body("body").id
         and model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH)
mid = model.geom_dataid[g]
verts = (model.mesh_vert[model.mesh_vertadr[mid]:][:model.mesh_vertnum[mid]]
         @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g])
hub = verts[np.abs(verts[:, 0]) > S.BODY_SIZE[0] / 2 + 1e-4]
radius = np.hypot(hub[:, 1] - data.xpos[model.body("body").id][1],
                  hub[:, 2] - axle_height).max() * 1000
print(f"  hubs: CAD radius {radius:.2f} mm, collision cylinder {S.HUB_RADIUS*1000:.2f} mm")
check(abs(radius - S.HUB_RADIUS * 1000) < 0.5, f"hub radius matches the CAD ({radius:.2f} mm)")

# --------------------------------------------------- 4. resting on the table
print("\nRESTING TEST (2 s, motors holding still)")
settle(model, data, seconds=2.0)
z = data.xpos[model.body("body").id][2] * 1000
speed = np.linalg.norm(data.qvel[:6])          # free joint: 3 linear + 3 angular
deepest = min([data.contact[i].dist for i in range(data.ncon)], default=0) * 1000
tilt = np.degrees(np.arccos(np.clip(data.xmat[model.body("body").id][8], -1, 1)))
warnings = {mujoco.mjtWarning(i).name: data.warning[i].number
            for i in range(len(data.warning)) if data.warning[i].number}
print(f"  axle height        {z:7.3f} mm  (expected {S.TABLE_HEIGHT_BELOW_AXLE*1000:.1f})")
print(f"  body tilt          {tilt:7.3f} deg")
print(f"  contacts           {data.ncon}   deepest overlap {deepest:.3f} mm")
print(f"  remaining motion   {speed:.2e} (m/s + rad/s)")
print(f"  MuJoCo warnings    {warnings or 'none'}")
check(abs(z - S.TABLE_HEIGHT_BELOW_AXLE * 1000) < 0.5, f"robot rests with axle at {z:.2f} mm")
check(deepest > -0.5, f"no sinking into the table (deepest overlap {deepest:.3f} mm)")
check(speed < 1e-3, "robot has come to rest (no jitter or explosion)")
check(not warnings, "no MuJoCo instability warnings")

print("\nSUMMARY")
for status, msg in results:
    print(f"  [{status}] {msg}")
print(f"\n{sum(s == 'PASS' for s, _ in results)}/{len(results)} checks passed")
