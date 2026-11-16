"""
Real robot vs simulator, side by side: Julian's phone videos (filmed from above, 2026-11-16)
next to the same run in the simulator, plus their headings over time.

  Run from the HW8 folder:
      ../../.venv/bin/python robot/real_vs_sim_video.py
  Inputs (defaults = Julian's two filmed runs):
      docs/media/real/real_baseline.MOV   + its log docs/data/session_julian/..._real_constant40_baseline_video.csv
      docs/media/real/real_policy.MOV     + its log docs/data/session_julian/..._real_policy_video.csv
  Outputs:
      docs/media/real/real_<run>.mp4               the phone video, compressed (540 x 960, H.264)
      docs/media/real/real_vs_sim_<run>.mp4        REAL (left) | SIMULATED (right), 1080 x 960
      docs/media/real/real_vs_sim_heading.png      heading over time: real (motion sensor) vs
                                                   the nominal simulated robot and 20 lopsided ones
      docs/data/session_julian/real_vs_sim_runs.csv  the numbers behind the plot (final values)

How it works
  - Simulator: demo_live.py's Walker (the same control loop as run_policy.run) on a FakeRobot,
    which reads the calibrated config.py (rpm table, wiring, sensor conventions). The simulated
    robot is the NOMINAL one (randomize=False), started with the real log's first leg angles
    and heading 0, with the measured body mass and the spec motor (as the drift comparison,
    robot/sim_hand_tests.py --motor regulated). Baseline = both legs at the same constant
    percent as the real run (units.action_for_percent), policy = the v2 policy.
  - Drawing: demo_live.py's two-robot display model, showing only the one robot; a fixed
    camera straight down, turned and scaled to match the phone (the robot walks to the LEFT,
    0.78 px per mm, axle starting at pixel (368, 608) in the 540 x 960 frame; measured on the
    first frame of the videos).
  - Sync: the real run starts at the first frame where the picture around the start spot
    changes (the legs begin to move); the simulated t = 0 is put there.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent
HW8 = ROBOT_DIR.parent
sys.path.insert(0, str(ROBOT_DIR))
import units as U  # noqa: E402
from demo_live import Walker, copy_pose, display_model, draw_extras, step_to  # noqa: E402
from policy import Policy  # noqa: E402

REAL = HW8 / "docs" / "media" / "real"
SESSION = HW8 / "docs" / "data" / "session_julian"
RUNS = {  # run: (phone video, run log, constant percent or None for the policy)
    "baseline": ("real_baseline.MOV", "2026-11-16_15-55-58_real_constant40_baseline_video.csv", 40),
    "policy": ("real_policy.MOV", "2026-11-16_15-56-40_real_policy_video.csv", None),
}
W, H = 540, 960                    # one panel (the phone's portrait frame, scaled)
FPS = 30
PX_PER_M = 780.0                   # 0.78 px per mm: the 80 x 48 mm body is ~60 x 40 px
START_PX = (368, 608)              # the axle at the start, in the 540 x 960 frame
START_BOX = (slice(540, 680), slice(300, 460))   # rows, cols around the start spot (sync)
SECONDS = 20.0                     # length of the real runs (run_policy --seconds 20)
BODY_MASS_KG = 0.0904              # Julian's 96 g minus the model's two 2.8 g legs
LOPSIDED = 20


def read_log(name):
    """Real run log -> (t, unwrapped heading deg, start leg angles [right, left] rad)."""
    rows = list(csv.DictReader(open(SESSION / name)))
    t = np.array([float(r["t"]) for r in rows])
    h = np.unwrap([math.atan2(float(r["in_head_sin"]), float(r["in_head_cos"])) for r in rows])
    q0 = [math.atan2(float(rows[0][f"in_leg_sin_{s}"]), float(rows[0][f"in_leg_cos_{s}"]))
          for s in ("r", "l")]
    return t - t[0], np.degrees(h), q0


def read_video(path):
    """All frames of the phone video, scaled to W x H."""
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA))
    return frames, cap.get(cv2.CAP_PROP_FPS)


def start_frame(frames):
    """First frame where the picture around the start spot clearly changes (legs start)."""
    box = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)[START_BOX].astype(float) for f in frames]
    change = np.array([0.0] + [np.abs(b - a).mean() for a, b in zip(box[:-1], box[1:])])
    still = np.median(change[:30])                     # the first second: robot not moving yet
    smooth = np.convolve(change, np.ones(5) / 5, mode="same")
    return int(np.argmax(smooth > max(4 * still, 0.5)))


def writer(path, size):
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"avc1"), FPS, size)
    assert out.isOpened(), f"cannot write H.264 to {path}"
    return out


def sim_run(q0, pct, seed=0, randomize=False):
    """One simulated run, as run_policy.run would drive it."""
    if pct is None:
        policy = Policy()
    else:
        c = U.action_for_percent(pct)
        policy = lambda obs: np.array([c, c])  # noqa: E731
    return Walker(seed, policy, dict(randomize=randomize, start_q=q0, start_yaw=0.0,
                                     body_mass_kg=BODY_MASS_KG, motor="regulated"))


def sim_heading(q0, pct, seed, randomize):
    """Heading (deg, + = left, unwrapped) every decision, and the final truth."""
    w = sim_run(q0, pct, seed, randomize)
    ts = np.arange(0, SECONDS + 1e-9, 0.05)
    h = []
    for t in ts:
        step_to({"w": w}, t, SECONDS)
        h.append(math.radians(w.robot.truth()["heading_deg"]))
    return ts, np.degrees(np.unwrap(h)), w.robot.truth()


def label(img, lines, color):
    """Dark bar at the top of a panel with white text; the first line in the panel's color."""
    bar = img[:16 + 26 * len(lines)]
    bar[:] = (bar * 0.3).astype(np.uint8)
    for j, txt in enumerate(lines):
        cv2.putText(img, txt, (12, 30 + 26 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.62 if j == 0 else 0.5,
                    color if j == 0 else (255, 255, 255), 2 if j == 0 else 1, cv2.LINE_AA)


def side_by_side(run, frames, k0, log, q0, pct):
    t_log, h_log, _ = log
    m, d, adr = display_model()
    m.vis.global_.offwidth, m.vis.global_.offheight = W, H
    key, other = ("base", "pol") if pct is not None else ("pol", "base")
    p = adr[other]["free"]
    d.qpos[p:p + 3] = [50.0, 50.0, 0.0]                  # the unused robot, far off screen
    w = sim_run(q0, pct)
    cam = mujoco.MjvCamera()
    cam.azimuth, cam.elevation = 0.0, -89.99             # straight down; forward = screen left
    cam.lookat[:] = ((START_PX[1] - H / 2) / PX_PER_M, (START_PX[0] - W / 2) / PX_PER_M, 0.0)
    cam.distance = (H / PX_PER_M) / (2 * math.tan(math.radians(m.vis.global_.fovy) / 2))
    name = f"baseline, both motors {pct} %" if pct is not None else "trained v2 policy"
    out = writer(REAL / f"real_vs_sim_{run}.mp4", (2 * W, H))
    with mujoco.Renderer(m, H, W) as r:
        for i, real in enumerate(frames):
            t = min(SECONDS, max(0.0, (i - k0) / FPS))
            step_to({key: w}, t, SECONDS)
            copy_pose(w, d, adr[key], 0.0)
            mujoco.mj_kinematics(m, d)
            r.update_scene(d, camera=cam)
            draw_extras(r.scene, {key: w}, {key: 0.0})
            sim = cv2.cvtColor(r.render(), cv2.COLOR_RGB2BGR)
            real = real.copy()
            t_txt = f"t = {t:4.1f} s" if i >= k0 else "waiting for start"
            label(real, [f"REAL robot: {name}", t_txt,
                         f"heading (motion sensor) {np.interp(t, t_log, h_log):+5.0f} deg  (+ = left)"],
                  (80, 200, 255))
            label(sim, [f"SIMULATION: {name}", "nominal robot, calibrated config.py",
                        f"heading {w.robot.truth()['heading_deg']:+5.0f} deg  (+ = left)"],
                  (255, 200, 80))
            out.write(np.hstack([real, sim]))
    out.release()
    return w.robot.truth()


def main():
    ap = argparse.ArgumentParser(description="Real phone video next to the same run in the simulator")
    ap.add_argument("--runs", nargs="+", choices=list(RUNS), default=list(RUNS))
    a = ap.parse_args()

    fig, axes = plt.subplots(1, len(a.runs), figsize=(6 * len(a.runs), 4.5), squeeze=False)
    rows = []
    for ax, run in zip(axes[0], a.runs):
        video, log_name, pct = RUNS[run]
        log = read_log(log_name)
        q0 = log[2]
        frames, fps = read_video(REAL / video)
        k0 = start_frame(frames)
        print(f"{run}: {len(frames)} frames at {fps:.2f} fps, run starts at frame {k0} "
              f"({k0 / fps:.2f} s); start legs {math.degrees(q0[0]):+.0f} / {math.degrees(q0[1]):+.0f} deg")

        out = writer(REAL / f"real_{run}.mp4", (W, H))
        for f in frames:
            out.write(f)
        out.release()

        nominal = side_by_side(run, frames, k0, log, q0, pct)
        rows.append({"run": run, "robot": "real", "heading_deg": round(log[1][-1], 1)})
        rows.append({"run": run, "robot": "sim nominal", "heading_deg": round(nominal["heading_deg"], 1),
                     "fwd_mm": round(nominal["fwd_mm"]), "side_mm": round(nominal["side_mm"])})

        for seed in range(1, LOPSIDED + 1):
            ts, h, tr = sim_heading(q0, pct, seed, randomize=True)
            ax.plot(ts, h, color="lightsteelblue", lw=0.8, label="sim, 20 lopsided robots" if seed == 1 else None)
            rows.append({"run": run, "robot": f"sim lopsided {seed}", "heading_deg": round(h[-1], 1),
                         "fwd_mm": round(tr["fwd_mm"]), "side_mm": round(tr["side_mm"])})
        ts, h, _ = sim_heading(q0, pct, 0, randomize=False)
        ax.plot(ts, h, color="black", lw=2, label="sim, nominal robot")
        ax.plot(log[0], log[1], color="red", lw=2, label="real (motion sensor)")
        ax.axhline(0, color="gray", lw=0.5)
        ax.set_title(f"{run}: " + (f"both motors {pct} %" if pct is not None else "v2 policy"))
        ax.set_xlabel("time (s)")
        ax.set_ylabel("heading (deg, + = turned left)")
        ax.legend(fontsize=8)
        print(f"  saved docs/media/real/real_{run}.mp4 and real_vs_sim_{run}.mp4")
    fig.tight_layout()
    fig.savefig(REAL / "real_vs_sim_heading.png", dpi=120)

    with open(SESSION / "real_vs_sim_runs.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["run", "robot", "heading_deg", "fwd_mm", "side_mm"])
        wr.writeheader()
        wr.writerows(rows)
    for run in a.runs:
        rs = [r for r in rows if r["run"] == run]
        lop = [r["heading_deg"] for r in rs if r["robot"].startswith("sim lopsided")]
        print(f"{run}: final heading real {rs[0]['heading_deg']:+.0f}, sim nominal {rs[1]['heading_deg']:+.0f} "
              f"(fwd {rs[1]['fwd_mm']} mm, side {rs[1]['side_mm']:+d} mm), lopsided median "
              f"{np.median(lop):+.0f} (range {min(lop):+.0f} to {max(lop):+.0f})")
    print("Saved docs/media/real/real_vs_sim_heading.png and docs/data/session_julian/real_vs_sim_runs.csv")


if __name__ == "__main__":
    main()
