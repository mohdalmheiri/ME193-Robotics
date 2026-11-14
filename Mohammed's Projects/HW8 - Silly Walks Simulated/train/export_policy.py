"""
Export the trained policy (and everything the robot side needs) so it runs WITHOUT MJLab.

Why: the real robot is driven from the main .venv (Python 3.14, which has PyTorch and the
LEGO library) but MJLab only lives in .venv-mjlab (Python 3.12). This script runs once in
.venv-mjlab and writes plain files into robot/model/ that the main .venv can read.

How it works:
  1. Loads the chosen checkpoint (model_<round>.pt) into MJLab's PPO runner, exactly as
     evaluate.py does.
  2. robot/model/policy.pt
       The actor network saved with TorchScript (RSL-RL's own export). It already contains
       the input scaling, so it computes:   action = MLP((obs - mean) / (std + 0.01))
       16 inputs -> 64 -> 64 -> 2 outputs (one per leg: right, left), ELU activations.
     robot/model/policy_weights.npz
       The same numbers as plain arrays (a backup that needs only numpy, and something a
       reader can open and inspect).
  3. robot/model/scene.xml
       The EXACT MuJoCo model MJLab trains on (robot + floor + motors + contact settings +
       elliptic friction + solver settings), saved from MJLab's own model description.
       FakeRobot loads this, so its physics cannot quietly differ from training.
  4. robot/model/policy_meta.json
       Every number the robot side must agree with: decision rate, max leg speed, the order
       and meaning of the 16 inputs, noise levels, randomization ranges, flip angle,
       leg box size, which checkpoint this is. Written FROM walk_straight_task.py, so there
       is only one source of truth.
  5. robot/tests/data/training_reference.npz
       Reference data for the robot-side tests, recorded from the real training environment:
       a 10 s policy run of 4 lopsided robots with all sensor noise switched OFF. For every
       decision it stores the full physical state (positions/speeds), the 16 inputs the policy
       saw, and the policy's output. The tests later put the same physical state into
       FakeRobot, convert its LEGO-unit readings with robot/units.py, and check they give the
       same 16 numbers; and check the exported policy gives the same outputs.

v2 (walk_straight_v2_task.py, --task v2) differs in what the robot side must know, so the
meta file then also says: the action means a FRACTION of the motor's top speed
("action_mode": "top_speed_fraction") and the policy trained on top speeds in
"top_speed_rpm_range"; the leg-speed input is the encoder average over one decision divided by
a fixed "leg_speed_norm_rpm"; and the extra randomizations (motor inertia, gearbox friction,
contact stiffness). The reference recording runs with the training pushes switched off.

Run from the HW8 folder:
  ../../.venv-mjlab/bin/python train/export_policy.py --task v2 --checkpoint \
      train/logs/rsl_rl/walk_straight_v2/2026-11-13_18-36-30_v2/model_799.pt
  ../../.venv-mjlab/bin/python train/export_policy.py --checkpoint \
      train/logs/rsl_rl/walk_straight/2026-11-12_22-50-21_first_check/model_299.pt
"""

import argparse
import json
import math
import re
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

TRAIN_DIR = Path(__file__).resolve().parent
HW8 = TRAIN_DIR.parent
sys.path.insert(0, str(TRAIN_DIR))

from mjlab.envs import ManagerBasedRlEnv  # noqa: E402
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper  # noqa: E402
import walk_straight_task as T1  # noqa: E402
import walk_straight_v2_task as T2  # noqa: E402

parser = argparse.ArgumentParser(description="Export the policy for the robot side")
parser.add_argument("--checkpoint", required=True, help="path to model_<round>.pt")
parser.add_argument("--task", choices=["v1", "v2"], default="v1")
args = parser.parse_args()
V2 = args.task == "v2"
T = T2 if V2 else T1          # T1 = v1 module; v2 reuses v1's constants where unchanged
ckpt = Path(args.checkpoint).resolve()
OUT = HW8 / "robot" / "model"
TEST_DATA = HW8 / "robot" / "tests" / "data"
OUT.mkdir(parents=True, exist_ok=True)
TEST_DATA.mkdir(parents=True, exist_ok=True)


def load_runner(env):
    runner = MjlabOnPolicyRunner(env, asdict(T.ppo_cfg()), device="cpu")
    runner.load(str(ckpt), load_cfg={"actor": True}, strict=True, map_location="cpu")
    return runner


# ------------------------------------------------------------------ 1-2. the network
env = RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg=T.make_env_cfg(num_envs=1), device="cpu"))
runner = load_runner(env)
runner.export_policy_to_jit(str(OUT), "policy.pt")
actor_sd = torch.load(ckpt, map_location="cpu", weights_only=False)["actor_state_dict"]
np.savez(OUT / "policy_weights.npz",
         obs_mean=actor_sd["obs_normalizer._mean"].numpy()[0],
         obs_std=actor_sd["obs_normalizer._std"].numpy()[0],
         obs_eps=np.float64(0.01),                        # RSL-RL EmpiricalNormalization eps
         w0=actor_sd["mlp.0.weight"].numpy(), b0=actor_sd["mlp.0.bias"].numpy(),
         w1=actor_sd["mlp.2.weight"].numpy(), b1=actor_sd["mlp.2.bias"].numpy(),
         w2=actor_sd["mlp.4.weight"].numpy(), b2=actor_sd["mlp.4.bias"].numpy())

# ------------------------------------------------------------------ 3. the physics model
xml = env.unwrapped.scene.spec.to_xml()
# The robot meshes (looks only; contact uses the boxes/cylinders) live in cad/assets.
# Point the model there with a path relative to robot/model/, so it works on any computer.
xml = re.sub(r'meshdir="[^"]*"', 'meshdir="../../cad/assets"', xml)
if 'meshdir=' not in xml:
    xml = xml.replace("<compiler ", '<compiler meshdir="../../cad/assets" ', 1)
xml = re.sub(r'file="[^"]*/([^"/]+\.stl)"', r'file="\1"', xml)    # bare file names
# MuJoCo 3.11 writes an empty "<default/>" inside <default>; MuJoCo 4 rejects it.
xml = re.sub(r"\n\s*<default/>", "", xml)
# MJLab applies the solver settings (time step, ELLIPTIC friction, iterations, ...) to the
# compiled model AFTER building it, so they are not in the spec's XML. Copy them from the
# compiled training model into an <option> line; otherwise plain MuJoCo would silently use
# its defaults (pyramidal friction -> the turning artifact we found earlier).
o = env.unwrapped.sim.mj_model.opt
CONE = {0: "pyramidal", 1: "elliptic"}
INTEGRATOR = {0: "Euler", 1: "RK4", 2: "implicit", 3: "implicitfast"}
SOLVER = {0: "PGS", 1: "CG", 2: "Newton"}
g = " ".join(f"{v:g}" for v in o.gravity)
option = (f'  <option timestep="{o.timestep:g}" cone="{CONE[int(o.cone)]}" '
          f'integrator="{INTEGRATOR[int(o.integrator)]}" solver="{SOLVER[int(o.solver)]}" '
          f'iterations="{o.iterations}" ls_iterations="{o.ls_iterations}" '
          f'tolerance="{o.tolerance:g}" ls_tolerance="{o.ls_tolerance:g}" '
          f'impratio="{o.impratio:g}" ccd_iterations="{o.ccd_iterations}" gravity="{g}"/>\n')
xml = re.sub(r"\s*<option[^>]*/>", "", xml)           # drop any partial one first
xml = xml.replace("\n  <size", "\n" + option + "\n  <size", 1)
# The free joint was added in code (robot_spec.py), which skips the exporter's default
# class; read back from a file it WOULD inherit armature 0.005 / frictionloss 0.1 - a big
# drag on the whole body. Pin the training values (0, 0) explicitly.
xml = xml.replace('<joint name="robot/free" type="free"/>',
                  '<joint name="robot/free" type="free" armature="0" frictionloss="0" damping="0"/>')
(OUT / "scene.xml").write_text(xml)

# Proof that the file IS the training model: reload it and compare every physics number.
# (A full dump of MuJoCo's options found one more difference, ccd_iterations 50 vs MuJoCo 4's
# default 35; it is now written into <option> and checked here too.)
import mujoco  # noqa: E402
train_m = env.unwrapped.sim.mj_model
file_m = mujoco.MjModel.from_xml_path(str(OUT / "scene.xml"))
FIELDS = ["body_mass", "body_inertia", "body_ipos", "body_pos", "body_quat",
          "jnt_axis", "jnt_pos", "dof_armature", "dof_frictionloss", "dof_damping",
          "geom_type", "geom_size", "geom_pos", "geom_quat", "geom_friction", "geom_solref",
          "geom_solimp", "geom_priority", "geom_condim", "geom_contype", "geom_conaffinity",
          "geom_margin", "geom_gap", "actuator_gainprm", "actuator_biasprm",
          "actuator_forcerange", "actuator_forcelimited", "actuator_ctrllimited",
          "opt.timestep", "opt.cone", "opt.integrator", "opt.solver", "opt.iterations",
          "opt.ls_iterations", "opt.tolerance", "opt.impratio", "opt.gravity",
          "opt.ccd_iterations", "opt.ccd_tolerance", "opt.ls_tolerance", "opt.noslip_iterations",
          "opt.enableflags", "opt.disableflags", "opt.o_margin", "opt.jacobian"]
bad = []
for f in FIELDS:
    a = np.asarray(eval(f"train_m.{f}"), dtype=float)
    b = np.asarray(eval(f"file_m.{f}"), dtype=float)
    if a.shape != b.shape or not np.allclose(a, b, atol=1e-9):
        bad.append(f)
if bad:
    sys.exit(f"scene.xml differs from the training model in: {bad}")
print(f"scene.xml matches the training model in all {len(FIELDS)} physics fields checked")
env.close()

# ------------------------------------------------------------------ 4. shared numbers
r = lambda x: round(float(x), 9)
meta = {
    "checkpoint": str(ckpt.relative_to(HW8)),
    "training_round": int(re.search(r"model_(\d+)", ckpt.name).group(1)),
    "physics_timestep_s": T.TIMESTEP,
    "decision_dt_s": T.DECISION_DT,
    "task": args.task,
    "max_speed_rpm": T.MAX_SPEED_RPM,
    "action_mode": "top_speed_fraction" if V2 else "fixed_top_speed",
    "action": ("2 numbers (right leg, left leg), clipped to -1..1; leg speed in the upright "
               "direction = (a + 1) / 2 x this motor's TOP speed (-1 = stopped, +1 = top speed). "
               "Training drew each robot's top speed from top_speed_rpm_range; on a real motor "
               "the robot side picks one top speed inside that range (config.POLICY_TOP_RPM). "
               "In the simulator's joint coordinates the upright direction is a NEGATIVE speed.")
    if V2 else "2 numbers (right leg, left leg), clipped to -1..1; leg speed in the upright "
              "direction = max_speed_rpm * (a + 1) / 2   (-1 = stopped, +1 = full speed). "
              "In the simulator's joint coordinates the upright direction is a NEGATIVE speed.",
    "joints": list(T.JOINTS),
    "observation_layout": [
        ["tilt", 3, "gravity direction in the body frame (unit vector; (0,0,-1) when level)"],
        ["gyro", 3, "body angular velocity in the body frame, rad/s"],
        ["heading", 2, "sin, cos of (heading - start heading), CCW from above positive"],
        ["leg_angle", 4, "sin(q_right), sin(q_left), cos(q_right), cos(q_left); q = joint "
                         "angle, 0 = leg pointing forward (+Y)"],
        ["leg_speed", 2, "(leg angle now - leg angle at the last decision) / decision_dt_s, "
                         "/ leg_speed_norm_rpm in rad/s (the encoder average)" if V2 else
                         "joint speed (right, left) / max speed in rad/s"],
        ["last_command", 2, "previous action (right, left), clipped to -1..1"],
    ],
    "body_axes": "x = robot's right, y = robot's front (walking direction), z = up",
    "flip_angle_deg": math.degrees(T1.FLIP_ANGLE),
    "noise": {"tilt": T1.TILT_NOISE, "gyro_rad_s": r(T1.GYRO_NOISE),
              "heading_rad": r(T1.HEADING_NOISE), "heading_drift_rad_s": r(T1.HEADING_DRIFT),
              "leg_angle_rad": r(T1.LEG_ANGLE_NOISE), "leg_calib_rad": r(T1.LEG_CALIB_ERROR),
              "leg_speed_frac": T.LEG_SPEED_NOISE},
    "randomization": {"motor_speed_scale": T1.MOTOR_SPEED_SCALE,
                      "motor_strength_scale": T1.MOTOR_STRENGTH_SCALE,
                      "friction": T1.FRICTION, "mass_scale": T.MASS_SCALE,
                      "com_shift_x_m": T1.COM_SHIFT_X,
                      "command_delay_physics_steps": T1.COMMAND_DELAY_STEPS,
                      "command_delay_hold_prob": 0.95},
    "reset": {"leg_box_extent_m": [r(v) for v in T1.leg_box_extent()],
              "table_height_below_axle_m": T.S.TABLE_HEIGHT_BELOW_AXLE,
              "drop_height_m": T.S.DROP_HEIGHT},
}
if V2:
    meta["top_speed_rpm_range"] = list(T2.TOP_SPEED_RPM)
    meta["leg_speed_norm_rpm"] = T2.MAX_SPEED_RPM
    meta["randomization"].update({
        "armature_kg_m2": list(T2.ARMATURE), "armature_distribution": "log_uniform",
        "joint_friction_scale": list(T2.JOINT_FRICTION_SCALE),
        "contact_timeconst_s": list(T2.CONTACT_TIMECONST),
        "pushes_training_only": {"interval_s": list(T2.PUSH_INTERVAL_S),
                                 "spin_rad_s": T2.PUSH_SPIN}})
else:
    meta["leg_speed_norm_rpm"] = T1.MAX_SPEED_RPM
(OUT / "policy_meta.json").write_text(json.dumps(meta, indent=2))

# ------------------------------------------------------------------ 5. reference data
# Same task, but every sensor imperfection switched off, so the recorded inputs are the
# exact functions of the physical state that the robot-side conversion must reproduce.
for name in ("HEADING_NOISE", "LEG_ANGLE_NOISE", "LEG_SPEED_NOISE"):
    setattr(T1, name, 0.0)                    # the obs functions read these at call time
T2.LEG_SPEED_NOISE = 0.0                      # v2's own leg-speed input
cfg = T.make_env_cfg(num_envs=4)
cfg.events.pop("push", None)                  # v2: no training pushes in the reference walk
cfg.observations["actor"].enable_corruption = False   # no tilt/gyro noise
cfg.seed = 3
torch.manual_seed(3)
env = RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg=cfg, device="cpu"))
base = env.unwrapped
policy = load_runner(env).get_inference_policy(device="cpu")
# Zero the per-robot sensor errors AFTER the runner is built: building it resets the robots,
# which draws new errors (found because the first recorded leg angles were 1.7 deg off).
st = T._state(base)   # (v2: includes q_prev / top_rpm)
st["yaw_drift"][:] = 0.0                      # no gyro drift and no encoder calibration
st["leg_calib"][:] = 0.0                      # error
origin = base.scene.env_origins.clone()
rec = {k: [] for k in ("qpos", "qvel", "obs", "action")}
obs = env.get_observations()
with torch.inference_mode():
    for _ in range(200):                      # 10 s
        a = policy(obs)
        # MuJoCo's own state arrays, one row per robot, in exactly the layout FakeRobot's
        # plain-MuJoCo model uses: qpos = [x y z, quaternion w x y z, q_right, q_left],
        # qvel = [linear velocity (world), angular velocity (BODY frame), leg speeds].
        qpos = torch.as_tensor(base.sim.data.qpos).clone()
        qpos[:, :3] -= origin                 # positions relative to each robot's own patch
        rec["qpos"].append(qpos.numpy())
        rec["qvel"].append(torch.as_tensor(base.sim.data.qvel).clone().numpy())
        rec["obs"].append(obs["actor"].numpy())
        rec["action"].append(a.numpy())
        obs, _, _, _ = env.step(a)
np.savez(TEST_DATA / "training_reference.npz",
         start_yaw=st["start_yaw"].numpy(),
         **{k: np.stack(v, 1) for k, v in rec.items()})    # arrays shaped [robot, step, ...]
env.close()

print(f"Exported {meta['checkpoint']} (round {meta['training_round']}) to robot/model/:\n"
      "  policy.pt, policy_weights.npz, scene.xml, policy_meta.json\n"
      "  and robot/tests/data/training_reference.npz (4 robots x 200 decisions, noise off)")
