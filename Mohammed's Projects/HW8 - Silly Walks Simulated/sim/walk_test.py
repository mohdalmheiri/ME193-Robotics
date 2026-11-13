"""
Walking test: both motors at the same speed. Does it move, which way, does it drift?

How it works:
  1. Builds the scene (build_scene.py) and lets the robot settle for 1 s with
     the motors holding still, so the test starts from a calm, resting robot.
  2. Commands both velocity motors to the same speed (settings.MOTOR_SPEED, or
     --rpm on the command line) and simulates --seconds of time.
  3. Every physics step it reads the body's pose. The body frame's origin is the
     axle centre, and its +Y axis is the robot's front. From that it tracks:
       - forward/back distance along the table's Y (the robot starts facing +Y)
       - sideways drift along X
       - heading change (yaw): the angle the robot's front has turned, measured
         on the table; positive = turned left
       - tilt and height, to spot flips and hops
       - the deepest overlap between a shape and the table (contact quality)
       - motor torque, to see whether the motors are at their torque limit
         (if so, the legs are slower than commanded)
  4. 30 times per simulated second it renders a frame from a camera that follows
     the robot, and writes them to docs/media/walk_test.mp4. It also saves a strip
     of frames, a top-down path plot, and a picture of the resting robot.

Run:  python sim/walk_test.py                 (speed from settings.py)
      python sim/walk_test.py --rpm 90 --seconds 5 --no-video
"""

import argparse
import math
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")            # draw plots to files, no window
import matplotlib.pyplot as plt
import mujoco
import numpy as np

import settings as S
from build_scene import build_model, settle

MEDIA = Path(__file__).resolve().parent.parent / "docs" / "media"
FPS = 30
WIDTH, HEIGHT = 960, 540

parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
parser.add_argument("--rpm", type=float, default=S.MOTOR_SPEED_RPM, help="motor speed (both legs)")
parser.add_argument("--seconds", type=float, default=10.0, help="simulated test length")
parser.add_argument("--no-video", action="store_true", help="skip rendering (much faster)")
args = parser.parse_args()
speed = args.rpm * 2 * math.pi / 60

model = build_model()
data = mujoco.MjData(model)
body = model.body("body").id


def pose():
    """Return (x, y, z, yaw_deg, tilt_deg) of the body frame (the axle centre)."""
    x, y, z = data.xpos[body]
    R = data.xmat[body].reshape(3, 3)
    front = R[:, 1]                                       # body +Y axis in the world
    yaw = math.degrees(math.atan2(-front[0], front[1]))   # 0 = facing +Y, + = turned left
    tilt = math.degrees(math.acos(np.clip(R[2, 2], -1, 1)))  # body up vs world up
    return x, y, z, yaw, tilt


# Camera that follows the robot from behind-right and above.
renderer = None if args.no_video else mujoco.Renderer(model, HEIGHT, WIDTH)
cam = mujoco.MjvCamera()
cam.type = mujoco.mjtCamera.mjCAMERA_FREE
cam.distance, cam.azimuth, cam.elevation = 0.38, -50, -22


def render():
    cam.lookat[:] = data.xpos[body] + [0, 0, 0.0]
    renderer.update_scene(data, camera=cam)
    return renderer.render()          # RGB image as a numpy array


# ---------------------------------------------------------------- 1. settle
settle(model, data, seconds=1.0)
x0, y0, *_ = pose()
if renderer:
    cv2.imwrite(str(MEDIA / "rest_pose.png"), cv2.cvtColor(render(), cv2.COLOR_RGB2BGR))

# ---------------------------------------------------------------- 2. drive
data.ctrl[:] = speed
steps = int(args.seconds / model.opt.timestep)
frame_every = int(round(1 / (FPS * model.opt.timestep)))
log, frames = [], []
saturated = 0
deepest = 0.0      # most negative contact distance = deepest overlap with the table
start_angle = data.qpos[model.joint("right").qposadr[0]]
for i in range(steps):
    mujoco.mj_step(model, data)
    x, y, z, yaw, tilt = pose()
    log.append((data.time, x - x0, y - y0, z, yaw, tilt))
    if data.ncon:
        deepest = min(deepest, data.contact.dist[:data.ncon].min())
    saturated += np.any(np.abs(data.actuator_force) > 0.99 * S.MOTOR_MAX_TORQUE)
    if renderer and i % frame_every == 0:
        frames.append(render())

t, dx, dy, z, yaw, tilt = np.array(log).T
turns = (data.qpos[model.joint("right").qposadr[0]] - start_angle) / (2 * math.pi)
avg_leg_speed = turns * 60 / args.seconds

# ---------------------------------------------------------------- 3. report
direction = "+Y (front, the way the legs point)" if dy[-1] > 0 else "-Y (back, toward the motor end)"
print(f"WALK TEST: both motors at {args.rpm:.0f} rpm for {args.seconds:.0f} s")
print(f"  moved forward/back  {dy[-1]*1000:+8.1f} mm  -> toward {direction}")
print(f"  sideways drift      {dx[-1]*1000:+8.1f} mm  (+ = to the robot's right)")
flipped = tilt.max() > 90
print(f"  heading change      {yaw[-1]:+8.2f} deg (+ = turned left)"
      + ("  <- meaningless after a flip: upside down, the 'front' arrow points backward" if flipped else ""))
print(f"  average speed       {abs(dy[-1])/args.seconds*1000:8.1f} mm/s")
print(f"  leg turns           {turns:8.2f}  (average {avg_leg_speed:.1f} rpm vs {args.rpm:.0f} commanded)")
print(f"  motors at torque limit {100*saturated/steps:5.1f} % of the time")
print(f"  axle height         {z.min()*1000:.1f} to {z.max()*1000:.1f} mm")
flip_time = f"FLIPPED OVER at {t[np.argmax(tilt > 90)] - t[0]:.2f} s" if flipped else "(never flipped)"
print(f"  deepest sinking     {-deepest*1000:.2f} mm (into the table, worst moment)")
print(f"  max tilt            {tilt.max():.1f} deg   {flip_time}")
warn = {mujoco.mjtWarning(i).name: data.warning[i].number
        for i in range(len(data.warning)) if data.warning[i].number}
print(f"  MuJoCo warnings     {warn or 'none'}")

# Top-down path plot.
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax[0].plot(dx * 1000, dy * 1000)
ax[0].plot(0, 0, "go", label="start")
ax[0].plot(dx[-1] * 1000, dy[-1] * 1000, "rs", label="end")
ax[0].set(xlabel="sideways X (mm, + = right)", ylabel="forward Y (mm, + = front)",
          title="Path of the axle centre, seen from above")
ax[0].axis("equal"); ax[0].grid(alpha=0.3); ax[0].legend()
ax[1].plot(t - t[0], z * 1000, label="axle height (mm)")
ax[1].plot(t - t[0], tilt, label="tilt (deg)")
ax[1].set(xlabel="time (s)", title="Bouncing and tipping during the gait")
ax[1].grid(alpha=0.3); ax[1].legend()
fig.suptitle(f"Both legs at {args.rpm:.0f} rpm")
fig.tight_layout()
tag = f"{args.rpm:+.0f}rpm"            # e.g. "+60rpm": files from each speed are kept apart
fig.savefig(MEDIA / f"walk_trajectory_{tag}.png", dpi=120)

# ---------------------------------------------------------------- 4. video
if renderer:
    # 'avc1' (H.264) plays in browsers and on GitHub; fall back to 'mp4v' if
    # this OpenCV build can't write H.264.
    path = MEDIA / f"walk_test_{tag}.mp4"
    for codec in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), FPS, (WIDTH, HEIGHT))
        if writer.isOpened():
            break
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    writer.release()
    # A strip of 6 frames spread over the first two leg turns, for the README.
    one_turn = 60 / max(args.rpm, 1e-6)
    pick = [int(k * min(2 * one_turn, args.seconds) / 6 * FPS) for k in range(6)]
    tiles = [cv2.resize(frames[p], (WIDTH // 2, HEIGHT // 2)) for p in pick]
    strip = np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:])])
    cv2.imwrite(str(MEDIA / f"walk_test_frames_{tag}.png"), cv2.cvtColor(strip, cv2.COLOR_RGB2BGR))
    print(f"\nSaved {path.name} ({len(frames)} frames, codec {codec}), walk_test_frames_{tag}.png, "
          f"rest_pose.png, walk_trajectory_{tag}.png in docs/media/")
else:
    print(f"\nSaved walk_trajectory_{tag}.png in docs/media/")
