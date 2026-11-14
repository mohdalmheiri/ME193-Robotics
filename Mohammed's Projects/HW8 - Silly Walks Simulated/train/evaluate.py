"""
Main result: BASELINE (both motors at one fixed speed) vs. a SIMPLE CONTROLLER vs. the
TRAINED POLICY on the same set of randomly lopsided robots.

The simple controller (step 5, "is the network needed at all?"): a proportional heading
controller. It reads the SAME noisy, drifting heading input the policy gets
(sin/cos of the heading change, inputs 7-8) and steers like a tank:
    h = heading change (rad, + = turned left)
    right leg command = c - K * h,   left leg command = c + K * h   (clipped to -1..1)
so a robot that turned left speeds up its left leg and slows its right leg. c is the same
average command as the baseline. The gain K is TUNED on a different set of robots
(--tune-seed, default 1: K = 0.25 ... 8, lowest mean heading error + 10 deg per flip) and
then tested on the evaluation robots, so it gets no unfair look at the test robots.

How it works:
  1. Builds the walk-straight task with --robots robots and every randomization ON
     (motor speed/strength per side, friction, mass, center of mass, leg start angles,
     command delay, sensor noise). The task's random generator is seeded (--seed),
     so both drivers get exactly the same robots and starting positions; the script
     prints a fingerprint of the robots for each run to prove it.
  2. Runs the TRAINED POLICY for --seconds (a checkpoint from train/logs/...). The
     policy only sees what the real robot can sense.
  3. Runs the BASELINE: both legs get the same constant command, set to the policy's
     own average command, so neither driver gets a speed advantage.
  4. For every robot it records, at the end (or at the moment it flipped):
       - sideways drift: distance from the start line (mm)
       - heading error: how far it has turned from the start direction (deg)
       - forward distance: progress along the start direction (mm)
       - flipped: whether it tipped past 70 deg
  5. Saves to docs/:
       eval_results_<tag>.md          the comparison table (means, medians, worst 5 %)
       media/eval_<tag>_paths.png     every robot's path, seen from above, both drivers
       media/eval_<tag>_baseline.mp4  one typical lopsided robot under each driver,
       media/eval_<tag>_policy.mp4    filmed from above-behind, start line in green,
                                      path so far in white dots (played at 2x speed)
     where <tag> is the physics step, e.g. "dt0.002".

Robustness check (trained at 0.002 s, tested at 0.001 s):
  ../../.venv-mjlab/bin/python train/evaluate.py --timestep 0.001

Run from the HW8 folder:
  ../../.venv-mjlab/bin/python train/evaluate.py --task v2 --checkpoint \
      train/logs/rsl_rl/walk_straight_v2/2026-11-13_18-36-30_v2/model_799.pt
  ../../.venv-mjlab/bin/python train/evaluate.py                     (v1, latest checkpoint)
  ../../.venv-mjlab/bin/python train/evaluate.py --checkpoint train/logs/rsl_rl/walk_straight/<run>/model_300.pt
"""

import argparse
import math
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mediapy
import mujoco
import numpy as np
import torch

TRAIN_DIR = Path(__file__).resolve().parent
HW8 = TRAIN_DIR.parent
sys.path.insert(0, str(TRAIN_DIR))

from mjlab.envs import ManagerBasedRlEnv  # noqa: E402
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper  # noqa: E402
import walk_straight_task as V1  # noqa: E402
import walk_straight_v2_task as T2  # noqa: E402

parser = argparse.ArgumentParser(description="Baseline vs simple controller vs trained policy")
parser.add_argument("--task", choices=["v1", "v2"], default="v1")
parser.add_argument("--checkpoint", help="model_*.pt (default: newest in train/logs)")
parser.add_argument("--tune-seed", type=int, default=1, help="robots used to tune the controller gain")
parser.add_argument("--gains", type=float, nargs="+", default=[0.25, 0.5, 1, 2, 4, 8])
parser.add_argument("--robots", type=int, default=100)
parser.add_argument("--seconds", type=float, default=20.0)
parser.add_argument("--timestep", type=float, default=V1.TIMESTEP)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--no-video", action="store_true")
args = parser.parse_args()
T = T2 if args.task == "v2" else V1
EXP = "walk_straight_v2" if args.task == "v2" else "walk_straight"
TAG = (f"{args.task}_" if args.task != "v1" else "") + f"dt{args.timestep:g}"
STEPS = round(args.seconds / V1.DECISION_DT)

if args.checkpoint:
    ckpt = Path(args.checkpoint).resolve()
else:
    ckpts = sorted((TRAIN_DIR / "logs" / "rsl_rl" / EXP).glob("*/model_*.pt"),
                   key=lambda p: (p.parent.name, int(p.stem.split("_")[1])))
    if not ckpts:
        sys.exit(f"No checkpoint found in train/logs/rsl_rl/{EXP}/")
    ckpt = ckpts[-1]
print(f"Checkpoint: {ckpt.relative_to(HW8)}\nPhysics step {args.timestep} s, "
      f"{args.robots} robots, {args.seconds:.0f} s each")


def make_env(seed=None):
    seed = args.seed if seed is None else seed
    cfg = T.make_env_cfg(num_envs=args.robots, timestep=args.timestep, episode_s=1e6)
    cfg.events.pop("push", None)    # v2's random pushes are training practice, not part of the test
    cfg.seed = seed
    torch.manual_seed(seed)
    return RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg=cfg, device="cpu"))


def drive(env, act_fn):
    """Run one episode with act_fn(obs) -> actions. Returns per-robot results and
    recordings. A robot's results freeze at the moment it flips."""
    base = env.unwrapped
    robot = base.scene["robot"]
    obs = env.get_observations()
    st = T._state(base)
    fingerprint = float(base.action_manager.get_term("leg_speed").motor_scale.sum()
                        + st["start_yaw"].sum())
    n = args.robots
    alive = torch.ones(n, dtype=torch.bool)
    res = {k: torch.zeros(n) for k in ("side", "head", "fwd")}
    flipped = torch.zeros(n, dtype=torch.bool)
    origin = base.scene.env_origins.clone()
    rec_xy, rec_q, rec_root, cmds = [], [], [], []
    for _ in range(STEPS):
        a = act_fn(obs)
        cmds.append(a.clamp(-1, 1)[alive].mean().item() if alive.any() else 0.0)
        obs, _, dones, _ = env.step(a)
        # read the state BEFORE an auto-reset could hide it: for flipped robots the
        # env has already reset them, so keep their last recorded values instead
        fwd, right = V1.track_frame(base)
        rel = robot.data.root_link_pos_w[:, :2] - st["start_xy"]
        now = {"side": (rel * right).sum(-1) * 1000, "head": V1.heading_error(base) * 180 / math.pi,
               "fwd": (rel * fwd).sum(-1) * 1000}
        just_flipped = alive & dones.bool()
        flipped |= just_flipped
        alive &= ~dones.bool()
        for k in res:
            res[k] = torch.where(alive, now[k], res[k])
        rec_xy.append(torch.stack([res["side"], res["fwd"]], -1).clone())
        root = robot.data.root_link_pose_w.clone()
        root[:, :3] -= origin
        rec_root.append(root)
        rec_q.append(robot.data.joint_pos.clone())
    return dict(res=res, flipped=flipped, fingerprint=fingerprint, mean_cmd=float(np.mean(cmds)),
                xy=torch.stack(rec_xy, 1).numpy(), root=torch.stack(rec_root, 1).numpy(),
                q=torch.stack(rec_q, 1).numpy(), start_yaw=st["start_yaw"].clone().numpy(),
                start_xy=(st["start_xy"] - origin[:, :2]).numpy(), model=base.sim.mj_model)


# ------------------------------------------------------------------ 1. policy
env = make_env()
agent = T.ppo_cfg()
runner = MjlabOnPolicyRunner(env, asdict(agent), device="cpu")
runner.load(str(ckpt), load_cfg={"actor": True}, strict=True, map_location="cpu")
policy = runner.get_inference_policy(device="cpu")
with torch.inference_mode():
    P = drive(env, policy)
env.close()

# ------------------------------------------------------------------ 2. baseline
c = P["mean_cmd"]
if args.task == "v2":
    speed_txt = f"{100 * (c + 1) / 2:.0f} % of each robot's top speed (80-140 rpm)"
else:
    speed_txt = f"{T.MAX_SPEED_RPM * (c + 1) / 2:.0f} rpm"
print(f"Policy's average command {c:+.2f} -> baseline runs both legs at {speed_txt}")
env = make_env()
B = drive(env, lambda obs: torch.full((args.robots, 2), c))
env.close()


# ------------------------------------------------------------------ 3. simple controller
def p_controller(K):
    """Proportional heading controller on the policy's own (noisy) heading input."""
    def act(obs):
        o = obs["actor"]
        h = torch.atan2(o[:, 6], o[:, 7])              # heading change, + = turned left
        return torch.stack([c - K * h, c + K * h], -1).clamp(-1.0, 1.0)
    return act


def score(R):
    return float(R["res"]["head"].abs().mean()) + 10.0 * int(R["flipped"].sum())


tune = []
for K in args.gains:                                   # tuned on DIFFERENT robots
    env = make_env(args.tune_seed)
    R = drive(env, p_controller(K))
    env.close()
    tune.append((K, score(R), float(R["res"]["head"].abs().mean()),
                 float(R["res"]["side"].abs().mean()), int(R["flipped"].sum())))
    print(f"  tuning K={K:g}: heading {tune[-1][2]:.1f} deg, drift {tune[-1][3]:.0f} mm, "
          f"flipped {tune[-1][4]}")
K_BEST = min(tune, key=lambda x: x[1])[0]
print(f"Chosen gain K = {K_BEST:g} (tuned on seed {args.tune_seed}); testing on seed {args.seed}")
env = make_env()
Cn = drive(env, p_controller(K_BEST))
env.close()
same = abs(P["fingerprint"] - B["fingerprint"]) < 1e-6 and abs(P["fingerprint"] - Cn["fingerprint"]) < 1e-6
print(f"Same robots in all three runs: {'YES' if same else 'NO (fingerprints differ!)'}")


# ------------------------------------------------------------------ 4. table
def stats(x):
    x = x.abs().numpy()
    return np.mean(x), np.median(x), np.percentile(x, 95)


DRIVERS = (("Baseline (equal speeds)", B), (f"Simple controller (K = {K_BEST:g})", Cn), ("Trained policy", P))
rows = []
for label, key, unit in (("Sideways drift", "side", "mm"), ("Heading error", "head", "deg")):
    cells = []
    for _, R in DRIVERS:
        x = stats(R["res"][key])
        cells.append(f"{x[0]:.0f} / {x[1]:.0f} / {x[2]:.0f}")
    rows.append(f"| {label} ({unit}) | " + " | ".join(cells) + " |")
cells = []
for _, R in DRIVERS:
    f = R["res"]["fwd"].numpy()
    cells.append(f"{f.mean():.0f} / {np.median(f):.0f} / {np.percentile(f, 5):.0f} (worst 5 %)")
rows.append("| Forward distance (mm) | " + " | ".join(cells) + " |")
rows.append("| Flipped | " + " | ".join(f"{int(R['flipped'].sum())} of {args.robots}" for _, R in DRIVERS) + " |")
tune_rows = [f"| {K:g} | {h:.1f} | {d:.0f} | {fl} |" + (" chosen |" if K == K_BEST else " |")
             for K, _, h, d, fl in tune]
table = "\n".join([
    f"# Evaluation: baseline vs. simple controller vs. trained policy ({TAG})", "",
    f"- Checkpoint: `{ckpt.relative_to(HW8)}`",
    f"- {args.robots} randomly lopsided robots (seed {args.seed}), {args.seconds:.0f} s each, "
    f"physics step {args.timestep} s, same robots for all drivers: {'yes' if same else 'NO'}"
    + ("; training's random pushes OFF" if args.task == "v2" else ""),
    f"- Baseline: both legs at a constant {speed_txt} (the policy's average command)",
    f"- Simple controller: right = c - K h, left = c + K h on the policy's own noisy heading "
    f"input, same c; K tuned on {args.robots} OTHER robots (seed {args.tune_seed})", "",
    "Values are mean / median / worst 5 % (95th percentile) of the absolute value at the end.", "",
    "| Measure | " + " | ".join(n for n, _ in DRIVERS) + " |", "|---|---|---|---|", *rows, "",
    f"Gain tuning (seed {args.tune_seed}; score = mean heading error + 10 deg per flip):", "",
    "| K | Heading error, mean (deg) | Sideways drift, mean (mm) | Flipped | |", "|---|---|---|---|---|",
    *tune_rows, ""])
out_md = HW8 / "docs" / f"eval_results_{TAG}.md"
out_md.write_text(table)
print("\n" + table)

# ------------------------------------------------------------------ 5. path plot
fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), sharex=True, sharey=True)
for ax, (name, R) in zip(axes, DRIVERS):
    for i in range(args.robots):
        ax.plot(R["xy"][i, :, 0], R["xy"][i, :, 1], lw=0.7, alpha=0.6,
                color="tab:red" if R["flipped"][i] else "tab:blue")
    ax.axvline(0, color="green", lw=1)
    ax.set(title=name, xlabel="sideways from start line (mm, + = right)")
    ax.grid(alpha=0.3)
axes[0].set_ylabel("forward along start direction (mm)")
fig.suptitle(f"{args.robots} lopsided robots, {args.seconds:.0f} s, physics step {args.timestep} s "
             "(red = flipped)")
fig.tight_layout()
fig.savefig(HW8 / "docs" / "media" / f"eval_{TAG}_paths.png", dpi=120)


# ------------------------------------------------------------------ 6. videos
def render(R, i, path):
    """Replay robot i's recorded motion in plain MuJoCo and film it."""
    m = R["model"]
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, 480, 640, max_geom=2000)
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    yaw0 = float(R["start_yaw"][i])
    cam.azimuth = math.degrees(yaw0) + 90         # look along the start direction (walks up the screen)
    cam.elevation, cam.distance = -55, 0.55
    sx, sy = R["start_xy"][i]
    fwd = np.array([-math.sin(yaw0), math.cos(yaw0)])
    frames = []
    for k in range(0, STEPS, 2):                      # every 2nd decision = 2x speed at 20 fps
        d.qpos[:7] = R["root"][i, k]
        d.qpos[7:9] = R["q"][i, k]
        mujoco.mj_forward(m, d)
        cam.lookat[:] = [d.qpos[0], d.qpos[1], 0.02]
        r.update_scene(d, cam)
        scn = r.scene
        # start line (green), 0.6 m long, drawn on the table
        a = np.array([sx, sy, 0.001]); b = a + np.r_[fwd * 0.6, 0]
        if scn.ngeom < scn.maxgeom:
            mujoco.mjv_initGeom(scn.geoms[scn.ngeom], mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3),
                                np.zeros(3), np.zeros(9), np.array([0.1, 0.8, 0.2, 1], np.float32))
            mujoco.mjv_connector(scn.geoms[scn.ngeom], mujoco.mjtGeom.mjGEOM_CAPSULE, 0.002, a, b)
            scn.ngeom += 1
        # path so far (white dots every 0.5 s)
        for kk in range(0, k + 1, 10):
            if scn.ngeom >= scn.maxgeom:
                break
            p = R["root"][i, kk, :3].copy(); p[2] = 0.002
            mujoco.mjv_initGeom(scn.geoms[scn.ngeom], mujoco.mjtGeom.mjGEOM_SPHERE,
                                np.array([0.003, 0, 0]), p, np.eye(3).ravel(),
                                np.array([1, 1, 1, 1], np.float32))
            scn.ngeom += 1
        frames.append(r.render())
    mediapy.write_video(str(path), frames, fps=20)


if not args.no_video:
    import imageio_ffmpeg
    mediapy.set_ffmpeg(imageio_ffmpeg.get_ffmpeg_exe())
    # film the robot whose baseline heading error is closest to the median: a typical
    # lopsided robot, not the best or worst case
    err = B["res"]["head"].abs().numpy()
    i = int(np.argmin(np.abs(err - np.median(err))))
    print(f"\nVideo robot #{i}: baseline heading error {B['res']['head'][i]:+.0f} deg, "
          f"controller {Cn['res']['head'][i]:+.0f} deg, policy {P['res']['head'][i]:+.0f} deg")
    for name, R in (("baseline", B), ("controller", Cn), ("policy", P)):
        render(R, i, HW8 / "docs" / "media" / f"eval_{TAG}_{name}.mp4")
    print(f"Saved docs/media/eval_{TAG}_baseline / _controller / _policy .mp4")
print(f"Saved docs/eval_results_{TAG}.md and docs/media/eval_{TAG}_paths.png")
