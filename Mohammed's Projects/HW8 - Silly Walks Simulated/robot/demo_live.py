"""
Live class demo: the trained policy and the baseline walking side by side, in real time,
in the MuJoCo viewer, on the SAME lopsided robot.

  Launch (from the HW8 folder; on a Mac the live viewer needs mjpython, not python):
      ../../.venv/bin/mjpython robot/demo_live.py
  Options:
      --seed N          which lopsided robot (default: DEMO_SEED, picked as a clear example,
                        see docs/process_log.md)
      --seconds 15      length of one run
      --loop            start the run again after a short pause (until the window is closed)
      --motor regulated|pwm   Julian's spec motor (config.MOTOR_SPEC) instead of the training motor
      --record PATH.mp4 no window: render the same view to a video (the backup for class)
      --headless        no window, as fast as possible: print the final results (for tests)
      --close-after S   close the window by itself after S seconds (to test the launch)
  In the window: SPACE pauses / resumes; close the window to end. The mouse still moves the
  camera (it keeps following the robots).

What the audience sees
  Two copies of the same lopsided robot, both started on a green start line, 0.4 m apart:
    LEFT  (orange)  baseline: both motors at one constant speed (the policy's own average
                    command on this robot, as in evaluate.py's baseline)
    RIGHT (blue)    the trained v2 policy, steering
  Each leaves a trail of its path. The text box shows time, heading error, sideways drift and
  both leg commands (%) for each robot.

How it works
  - Two FakeRobots with the same seed = physically the same lopsided robot (same masses,
    friction, motors, Bluetooth delay, sensor noise). FakeRobot is the checked simulator
    used by every robot-side check (docs/fake_robot_check.md).
  - Each robot is driven by the same functions as robot/run_policy.py (hub reading ->
    units.observation -> policy -> units.command -> whole percents -> FakeRobot), one decision
    every 0.05 s, with the same order of steps and the same tip-over stop. Only the CSV log is
    left out. The test robot/tests/test_demo.py checks that a headless demo run ends EXACTLY
    where run_policy.run ends for the same robot.
  - Real time: the physics is advanced to match the wall clock between screen updates.
  - Display: a separate two-robot model, only drawn (never simulated). Every frame the two
    simulated robots' poses are copied into it, turned so that each robot's own start heading
    points up the screen (FakeRobot starts every robot at a random heading).
"""

import argparse
import math
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent
HW8 = ROBOT_DIR.parent
sys.path.insert(0, str(ROBOT_DIR))
import config as C  # noqa: E402
import units as U  # noqa: E402
from fake_robot import FakeRobot  # noqa: E402
from policy import Policy  # noqa: E402
from run_policy import FLIP_DEG, tilt_deg  # noqa: E402

# The default robot: picked from seeds 0-99 as a CLEAR example (baseline curves a lot, policy
# walks straight, nobody flips). How it was picked: docs/process_log.md, 2026-11-14 demo entry.
DEMO_SEED = 6
GAP_M = 0.4                                  # sideways distance between the two robots on screen
DT = U.META["decision_dt_s"]                 # 0.05 s between decisions
COLORS = {"base": (0.95, 0.55, 0.15, 1.0), "pol": (0.25, 0.55, 0.95, 1.0)}


# ---------------------------------------------------------------- one robot + its control loop
class Walker:
    """One FakeRobot driven one decision at a time, with the same steps as run_policy.run."""

    def __init__(self, seed, policy, fake_kw):
        self.robot = FakeRobot(seed=seed, **fake_kw)
        self.policy = policy
        self.legs = U.LegSpeed()
        self.last_cmd = np.zeros(2)          # training starts every episode with "previous" = 0
        self.robot.connect()
        self.t0 = self.robot.now()
        self.k = 0                           # decisions made
        self.stopped = None                  # reason, once the run has ended for this robot
        self.pct = {"right": 0, "left": 0}
        self.path = []                       # (sideways, forward) in m, one point per decision time
        self.done = False                    # True once the run's time is up

    def k_time(self):
        """Time of this robot's next decision: one path point is added per decision time,
        also after a stop, so this keeps counting 0, 0.05, 0.10 ... s."""
        return len(self.path) * DT

    def advance(self, t):
        """Run the physics up to t seconds after the start."""
        self.robot.wait_until(self.t0 + t)

    def decide(self):
        """One decision, in run_policy.run's order: read -> stale check -> inputs -> tip-over
        check -> policy -> percent -> send. Call exactly at t0 + k x DT."""
        tr = self.robot.truth()
        self.path.append((tr["side_mm"] / 1000, tr["fwd_mm"] / 1000))
        if self.stopped:
            return
        r = self.robot.read()
        if self.robot.now() - r.t > C.STALE_SENSOR_S:
            return self.stop("stale sensors")
        obs = U.observation(r, self.legs.update(r), self.last_cmd)
        if tilt_deg(obs[:3]) > FLIP_DEG:
            return self.stop(f"tipped over ({tilt_deg(obs[:3]):.0f} deg)")
        action = self.policy(obs)
        self.pct, _ = U.command(action)
        self.robot.send(self.pct["right"], self.pct["left"])
        self.last_cmd = np.clip(action, -1, 1)
        self.k += 1

    def stop(self, reason):
        self.stopped = reason
        self.robot.stop()                    # motors to 0 (through the Bluetooth delay, as real)
        self.pct = {"right": 0, "left": 0}


def baseline_action(seed, fake_kw, seconds):
    """The baseline's constant action: the policy's average command on this same robot
    (a fast run first, as evaluate.py and check_fake_vs_eval.py choose their baseline)."""
    acts = []
    pol = Policy()
    w = Walker(seed, lambda obs: acts.append(np.clip(a := pol(obs), -1, 1)) or a, fake_kw)
    for k in range(round(seconds / DT)):
        w.advance(k * DT)
        w.decide()
    return float(np.mean(acts))


# ---------------------------------------------------------------- the two-robot display model
def display_model():
    """scene.xml plus a second copy of the robot (names prefixed 'base_'), colored per driver.
    Only drawn, never stepped."""
    scene = U.MODEL_DIR / "scene.xml"
    spec = mujoco.MjSpec.from_file(str(scene))
    child = mujoco.MjSpec.from_file(str(scene))
    frame = spec.worldbody.add_frame()
    frame.attach_body(child.body("robot/body"), "base_", "")
    for prefix, key in (("", "pol"), ("base_", "base")):
        spec.material(prefix + "robot/body_material").rgba = COLORS[key]
    m = spec.compile()
    d = mujoco.MjData(m)
    adr = {}
    for prefix, key in (("", "pol"), ("base_", "base")):
        adr[key] = {"free": m.jnt_qposadr[m.joint(prefix + "robot/free").id],
                    "right": m.jnt_qposadr[m.joint(prefix + "robot/right").id],
                    "left": m.jnt_qposadr[m.joint(prefix + "robot/left").id]}
    return m, d, adr


def copy_pose(walker, d_disp, adr, x_offset):
    """Copy one simulated robot's pose into the display, in a frame where its start point is
    (x_offset, 0) and its start heading points along +y (up the screen)."""
    fr = walker.robot
    sd = fr.d
    yaw0 = fr.start_yaw
    c, s = math.cos(-yaw0), math.sin(-yaw0)
    rel = sd.qpos[:2] - fr.start_xy
    p = adr["free"]
    d_disp.qpos[p:p + 3] = [c * rel[0] - s * rel[1] + x_offset, s * rel[0] + c * rel[1], sd.qpos[2]]
    turn = np.array([math.cos(-yaw0 / 2), 0, 0, math.sin(-yaw0 / 2)])
    q = np.zeros(4)
    mujoco.mju_mulQuat(q, turn, sd.qpos[3:7])
    d_disp.qpos[p + 3:p + 7] = q
    for side in ("right", "left"):
        d_disp.qpos[adr[side]] = sd.qpos[fr.qadr[side]]


def draw_extras(scn, walkers, offsets, max_geom=None):
    """Add the green start lines and both robots' trails to a scene (viewer or renderer)."""
    limit = max_geom or scn.maxgeom

    def line(a, b, rgba, width):
        if scn.ngeom >= limit:
            return
        g = scn.geoms[scn.ngeom]
        mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3),
                            np.zeros(9), np.array(rgba, dtype=np.float32))
        mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_CAPSULE, width,
                             np.array(a, dtype=float), np.array(b, dtype=float))
        scn.ngeom += 1

    for key, x0 in offsets.items():
        line((x0 - 0.12, 0, 0.001), (x0 + 0.12, 0, 0.001), (0.1, 0.8, 0.2, 1), 0.003)   # start line
        line((x0, 0, 0.0008), (x0, 3.0, 0.0008), (0.1, 0.8, 0.2, 0.35), 0.0015)          # straight-ahead guide
        pts = walkers[key].path
        for (sa, fa), (sb, fb) in zip(pts[:-1], pts[1:]):
            line((x0 + sa, fa, 0.002), (x0 + sb, fb, 0.002), COLORS[key], 0.002)


def frame_camera(cam, walkers, offsets):
    """Point the camera at the middle of both robots and back off far enough to keep both in
    view (a robot that curves away stays on screen)."""
    pts = np.array([(offsets[k] + (w.path[-1][0] if w.path else 0.0), w.path[-1][1] if w.path else 0.0)
                    for k, w in walkers.items()])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    cam.lookat[:] = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2 + 0.1, 0.02)
    cam.distance = max(1.1, 1.6 * max(hi[0] - lo[0], hi[1] - lo[1]))


def status_text(walkers, t, base_pct, paused):
    """Text box contents: (left column, right column)."""
    names = {"base": f"LEFT, orange: baseline (both motors {base_pct} %)",
             "pol": "RIGHT, blue: trained policy"}
    left, right = [f"t = {t:4.1f} s" + ("   PAUSED (space)" if paused else "")], [""]
    for key in ("base", "pol"):
        w = walkers[key]
        tr = w.robot.truth()
        left += [names[key], "   heading error / drift (- = left)", "   leg commands R / L"]
        right += ["" if not w.stopped else w.stopped,
                  f"{tr['heading_deg']:+6.1f} deg / {tr['side_mm']:+5.0f} mm",
                  f"{w.pct['right']:4d} % / {w.pct['left']:4d} %"]
    return "\n".join(left), "\n".join(right)


# ---------------------------------------------------------------- one demo run
def new_run(seed, fake_kw, seconds):
    c = baseline_action(seed, fake_kw, seconds)
    base_pct = U.command(np.array([c, c]))[0]["right"] * C.UPRIGHT_PERCENT_SIGN["right"]
    walkers = {"base": Walker(seed, lambda obs: np.array([c, c]), fake_kw),
               "pol": Walker(seed, Policy(), fake_kw)}
    return walkers, base_pct


def step_to(walkers, t_target, seconds):
    """Advance both robots to t_target, making every decision on the way at its exact time."""
    for w in walkers.values():
        while True:
            t_dec = w.k_time()
            if t_dec > t_target + 1e-9:
                break
            w.advance(t_dec)
            if t_dec >= seconds - 1e-9:      # run_policy.run: decision n = time limit -> stop
                if not w.stopped:
                    w.stop("finished")
                w.decide()                    # records the final path point
                w.done = True
                break
            w.decide()
        if not w.done:
            w.advance(t_target)


def finished(walkers):
    return all(w.done for w in walkers.values())


def headless(seed, fake_kw, seconds):
    walkers, base_pct = new_run(seed, fake_kw, seconds)
    step_to(walkers, seconds, seconds)
    return walkers, base_pct


# ---------------------------------------------------------------- live viewer
def live(a, fake_kw):
    import mujoco.viewer
    m, d, adr = display_model()
    offsets = {"base": -GAP_M / 2, "pol": GAP_M / 2}
    state = {"paused": False}

    def key(code):
        if code == 32:                        # space
            state["paused"] = not state["paused"]

    try:
        viewer = mujoco.viewer.launch_passive(m, d, key_callback=key, show_left_ui=False,
                                              show_right_ui=False)
    except RuntimeError as e:
        sys.exit(f"{e}\nOn a Mac, start the demo with mjpython:  ../../.venv/bin/mjpython robot/demo_live.py")
    opened = time.monotonic()
    with viewer:
        viewer.cam.distance, viewer.cam.elevation, viewer.cam.azimuth = 1.1, -30, 90
        while viewer.is_running():
            walkers, base_pct = new_run(a.seed, fake_kw, a.seconds)
            t, last_wall, hold_until = 0.0, time.monotonic(), None
            while viewer.is_running():
                now = time.monotonic()
                if not state["paused"] and not finished(walkers):
                    t = min(a.seconds, t + (now - last_wall))
                    step_to(walkers, t, a.seconds)
                last_wall = now
                with viewer.lock():               # the viewer draws from another thread
                    for key_, w in walkers.items():
                        copy_pose(w, d, adr[key_], offsets[key_])
                    mujoco.mj_kinematics(m, d)
                    viewer.user_scn.ngeom = 0
                    draw_extras(viewer.user_scn, walkers, offsets)
                    frame_camera(viewer.cam, walkers, offsets)
                # set_texts takes the viewer's lock itself: calling it inside the block above
                # deadlocks (found while testing the launch)
                viewer.set_texts((None, None, *status_text(walkers, t, base_pct, state["paused"])))
                viewer.sync()
                if finished(walkers):
                    hold_until = hold_until or now + 4.0
                    if a.loop and now > hold_until:
                        break                 # start the run again
                    # (without --loop the final picture stays until the window is closed)
                if a.close_after and now - opened > a.close_after:
                    viewer.close()
                time.sleep(1 / 60)


# ---------------------------------------------------------------- video (backup)
def record(a, fake_kw):
    import cv2
    m, d, adr = display_model()
    m.vis.global_.offwidth, m.vis.global_.offheight = 1280, 720
    offsets = {"base": -GAP_M / 2, "pol": GAP_M / 2}
    walkers, base_pct = new_run(a.seed, fake_kw, a.seconds)
    fps = 30
    out = Path(a.record)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    for codec in ("avc1", "mp4v"):           # H.264 if this OpenCV has it (plays everywhere)
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*codec), fps, (1280, 720))
        if writer.isOpened():
            break
    cam = mujoco.MjvCamera()
    cam.distance, cam.elevation, cam.azimuth = 1.1, -30, 90
    with mujoco.Renderer(m, 720, 1280) as r:
        n = round(a.seconds * fps) + 3 * fps   # the run, then 3 s on the final picture
        for i in range(n):
            t = min(a.seconds, i / fps)
            step_to(walkers, t, a.seconds)
            for key_, w in walkers.items():
                copy_pose(w, d, adr[key_], offsets[key_])
            mujoco.mj_kinematics(m, d)
            frame_camera(cam, walkers, offsets)
            r.update_scene(d, camera=cam)
            draw_extras(r.scene, walkers, offsets)
            img = cv2.cvtColor(r.render(), cv2.COLOR_RGB2BGR)
            left, right = status_text(walkers, t, base_pct, False)
            rows = list(zip(left.split("\n"), right.split("\n")))
            box = img[8:20 + 26 * len(rows), 8:740]           # darkened box behind the text
            box[:] = (box * 0.35).astype(np.uint8)
            for j, (l_, r_) in enumerate(rows):
                for txt, x in ((l_, 20), (r_, 470)):
                    cv2.putText(img, txt, (x, 32 + 26 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (255, 255, 255), 1, cv2.LINE_AA)
            writer.write(img)
    writer.release()
    print(f"Saved {out} ({a.seconds:.0f} s run + 3 s hold, {fps} fps)")


def main():
    p = argparse.ArgumentParser(description="Live demo: policy vs baseline on the same lopsided robot")
    p.add_argument("--seed", type=int, default=DEMO_SEED)
    p.add_argument("--seconds", type=float, default=15.0)
    p.add_argument("--loop", action="store_true")
    p.add_argument("--close-after", type=float, default=None, metavar="S",
                   help="close the window after S seconds (for testing the launch)")
    p.add_argument("--motor", choices=("training", "regulated", "pwm"), default="training")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--record", metavar="PATH.mp4")
    g.add_argument("--headless", action="store_true")
    a = p.parse_args()
    fake_kw = {} if a.motor == "training" else {"motor": a.motor, "body_mass_kg": C.MOTOR_SPEC["weight_kg"]}
    if a.headless:
        walkers, base_pct = headless(a.seed, fake_kw, a.seconds)
        for key_, name in (("base", f"baseline {base_pct} %"), ("pol", "policy")):
            tr = walkers[key_].robot.truth()
            print(f"{name:14s} heading {tr['heading_deg']:+6.1f} deg, drift {tr['side_mm']:+5.0f} mm, "
                  f"forward {tr['fwd_mm']:5.0f} mm, end: {walkers[key_].stopped}")
    elif a.record:
        record(a, fake_kw)
    else:
        live(a, fake_kw)


if __name__ == "__main__":
    main()
