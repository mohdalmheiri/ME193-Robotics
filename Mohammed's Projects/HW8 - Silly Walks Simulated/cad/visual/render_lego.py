"""
Product-photo style picture of the LEGO-looking robot (Notion cover). PICTURES ONLY: uses the
STLs in this folder, never the simulation model.

The picture: the Double Motor in its real colours (white top, dark turquoise bottom, ...), two
Technic 1x8 bricks as legs on the hubs, pivoting at their 2nd hole, the RIGHT leg at angle 0
(long arm forward, flat) and the LEFT leg a quarter turn ahead (long arm straight up, the
"legs out of step" pose of the drift test), on a plain white background with a soft shadow,
seen from the front-right and slightly above. The attribution line is added at the bottom.

How it works:
  1. Builds a small MuJoCo scene in memory (MjSpec): each colour STL of the motor as a mesh with
     its LDraw colour, the leg STL twice, moved to x = +/-36 mm (hub face 32 mm + half the
     8 mm brick) and turned about the axle (x) by the leg angle; a white floor just under the
     lowest point (for the shadow), a white flat sky, two lights.
  2. Renders offscreen at high resolution with anti-aliasing (MuJoCo's own renderer).
  3. Plain white background: it renders three passes (the full scene; the same without the
     robot, i.e. the bare floor; a mask of which pixels are robot). Robot pixels come from the
     full scene; every other pixel is pure white, darkened only by the robot's shadow
     (full / bare floor), so the floor's fall-off toward the horizon disappears.
  4. Writes the attribution with Pillow and saves the PNG.

Run from the HW8 folder:
  ../../.venv/bin/python cad/visual/render_lego.py
  options: --width 3200 --height 1800  --leg-color "#A0A5A9"  --out <png>
"""

import argparse
import math
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
HW8 = HERE.parent.parent
OUT = HW8 / "docs" / "media" / "presentation" / "lego_model.png"
# LDraw colours (official LDConfig.ldr); the motor's "main colour" is white on the real part
MOTOR = {"main": "#F4F4F4", "dark_turquoise": "#069D9F", "black": "#1B2A34",
         "light_bluish_grey": "#A0A5A9", "metallic_silver": "#898788", "trans_medium_blue": "#559AB7"}
LEG_X_MM = 36.0                     # hub outer face (32 mm) + half the brick (4 mm)
ATTRIBUTION = ("LEGO motor and brick models from the LDraw library (library.ldraw.org), CC BY 4.0: "
               "Double Motor by Philippe Hurbain, Technic brick by James Jessiman. "
               "LEGO® is a trademark of the LEGO Group, which does not sponsor or endorse this project.")


def rgba(hexcol, alpha=1.0):
    h = hexcol.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [alpha]


def build(leg_color: str, right_deg: float, left_deg: float) -> mujoco.MjModel:
    spec = mujoco.MjSpec()
    spec.compiler.degree = False
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 4000, 4000
    spec.visual.quality.offsamples = 8                 # anti-aliasing
    spec.visual.quality.shadowsize = 8192              # sharp, clean shadow
    spec.visual.headlight.ambient = [0.45, 0.45, 0.45]
    spec.visual.headlight.diffuse = [0.35, 0.35, 0.35]
    spec.visual.headlight.specular = [0.05, 0.05, 0.05]
    spec.visual.rgba.haze = [1, 1, 1, 1]
    # clipping distances are in units of the model's size (tiny here): reach past the floor's
    # edge, or the far floor is cut off and shows black
    spec.visual.map.znear = 0.001
    spec.visual.map.zfar = 2000.0
    # plain white background: a flat white sky box
    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
                     builtin=mujoco.mjtBuiltin.mjBUILTIN_FLAT, rgb1=[1, 1, 1], rgb2=[1, 1, 1],
                     width=16, height=16)
    w = spec.worldbody
    mm = 0.001
    for name, col in MOTOR.items():
        spec.add_mesh(name=f"motor_{name}", file=str(HERE / f"double_motor_{name}.stl"),
                      scale=[mm] * 3, inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
        alpha = 0.6 if name.startswith("trans") else 1.0
        w.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=f"motor_{name}", rgba=rgba(col, alpha),
                   contype=0, conaffinity=0, group=1)
    spec.add_mesh(name="leg", file=str(HERE / "technic_brick_1x8_leg.stl"), scale=[mm] * 3,
                  inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
    for side, x, deg in (("right", +LEG_X_MM, right_deg), ("left", -LEG_X_MM, left_deg)):
        q = math.radians(deg)                          # turn about the axle (x); +90 = long arm up
        w.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname="leg", rgba=rgba(leg_color),
                   pos=[x * mm, 0, 0], quat=[math.cos(q / 2), math.sin(q / 2), 0, 0],
                   contype=0, conaffinity=0, name=f"leg_{side}", group=1)
    # white floor under the lowest point (legs reach 48 mm from the axle), only for the shadow
    # a little glow (emission) keeps the lit floor pure white while the shadow stays a soft grey
    spec.add_material(name="floor", rgba=[1, 1, 1, 1], emission=0.1, specular=0.0, reflectance=0.0)
    w.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[20, 20, 0.01], pos=[0, 0, -0.0175],
               material="floor", contype=0, conaffinity=0)
    w.add_light(pos=[0.15, 0.2, 0.6], dir=[-0.25, -0.33, -1], castshadow=True,
                diffuse=[0.45, 0.45, 0.45], specular=[0.15, 0.15, 0.15])
    w.add_light(pos=[-0.4, 0.2, 0.3], dir=[0.6, -0.2, -0.4], castshadow=False,
                diffuse=[0.2, 0.2, 0.2], specular=[0, 0, 0])
    return spec.compile()


def main():
    ap = argparse.ArgumentParser(description="Product-photo render of the LEGO-looking robot")
    ap.add_argument("--width", type=int, default=3200)
    ap.add_argument("--height", type=int, default=1800)
    ap.add_argument("--leg-color", default="#A0A5A9",
                    help="LEGO light bluish grey by default, like the real robot's legs")
    ap.add_argument("--right-deg", type=float, default=0.0, help="right leg angle (0 = forward, flat)")
    ap.add_argument("--left-deg", type=float, default=90.0, help="left leg angle (90 = long arm up)")
    ap.add_argument("--azimuth", type=float, default=228.0, help="camera at the robot's front-right")
    ap.add_argument("--elevation", type=float, default=-32.0, help="looking down; keeps the horizon out")
    ap.add_argument("--distance", type=float, default=0.19)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()

    m = build(a.leg_color, a.right_deg, a.left_deg)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [0.0, -0.012, 0.004]               # the middle of the robot (body is behind the axle)
    cam.azimuth, cam.elevation, cam.distance = a.azimuth, a.elevation, a.distance
    with mujoco.Renderer(m, a.height, a.width) as r:
        def shot(show_robot=True, segment=False):
            opt = mujoco.MjvOption()
            opt.geomgroup[1] = show_robot
            if segment:
                r.enable_segmentation_rendering()
            r.update_scene(d, camera=cam, scene_option=opt)
            r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
            out = r.render()
            r.disable_segmentation_rendering()
            return out
        full = shot().astype(float)                     # 1. robot, floor, shadow
        floor = shot(show_robot=False).astype(float)    # 2. the bare floor (no robot, no shadow)
        seg = shot(segment=True)[..., 0]                # 3. which geom each pixel shows (-1 = sky)
    # Everything that is not the robot becomes PURE WHITE, darkened only by the robot's own
    # shadow (full / bare floor). The floor's own fall-off toward the horizon disappears.
    robot = np.isin(seg, [i for i in range(m.ngeom) if m.geom_group[i] == 1])
    shade = np.clip(full.mean(2) / np.maximum(floor.mean(2), 1.0), 0.0, 1.0)
    bg = 255.0 * (1.0 - 0.6 * (1.0 - shade))            # a soft grey shadow, never black
    img = np.where(robot[..., None], full, bg[..., None].repeat(3, axis=2))
    img = Image.fromarray(img.round().astype(np.uint8))

    # attribution, small, grey, centred at the bottom
    draw = ImageDraw.Draw(img)
    size = max(10, a.height // 70)
    while True:                                         # shrink until it fits the width
        try:
            font = ImageFont.truetype("Helvetica.ttc", size)
        except OSError:
            font = ImageFont.load_default(size=size)
        box = draw.textbbox((0, 0), ATTRIBUTION, font=font)
        if box[2] - box[0] <= 0.96 * a.width or size <= 8:
            break
        size -= 1
    draw.text(((a.width - (box[2] - box[0])) / 2, a.height - (box[3] - box[1]) - size), ATTRIBUTION,
              fill=(130, 130, 130), font=font)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out)
    print(f"saved {a.out} ({a.width} x {a.height})")


if __name__ == "__main__":
    main()
