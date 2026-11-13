"""
Walk-straight task, VERSION 2: same goal and reward idea as walk_straight_task.py (v1), with
the fixes found while building the robot-side code (docs/process_log.md, 2026-11-13).
v1 is left unchanged so its results stay reproducible; v2 reuses v1's code where nothing
changed (heading, sideways offset, most observations and rewards).

What changed from v1, and why
  1. MOTOR INERTIA ("armature"): 2e-4 kg m^2 nominal, randomized 5e-5..5e-4 per leg
     (v1: 1e-5). With v1's tiny value the simulated speed controller overshot every 2 ms
     step whenever the command changed ("leg chatter": leg speed flipped sign on 17 % of
     physics steps, motor at its torque limit 36 % of the time). From 5e-5 up the chatter
     is gone; a geared LEGO motor's real value is very likely in this range.
  2. JOINT FRICTION randomized x0.5..2.5 per leg, and CONTACT STIFFNESS randomized
     (solref time constant 0.004..0.008 s; not lower: below 2 x the 0.002 s step contacts
     become unstable): so the policy cannot rely on one exact physics. v1 was upright in
     500/500 MJLab robots but tipped 6-9 % of robots in a slightly different simulator.
  3. MOTOR TOP SPEED unknown until measured, so randomized per robot: 80..140 rpm (both
     sides, then each side x0.9..1.1 as in v1). The ACTION now means "fraction of this
     motor's top speed": target = -top_speed * (a + 1) / 2, i.e. on the real hub
     percent = 100 * (a + 1) / 2, whatever the real top speed is.
  4. BODY MASS range widened: x0.6..1.6 (v1: x0.8..1.3), real weight unknown.
  5. LEG SPEED INPUT = how far each leg turned during the last decision / 0.05 s (the
     encoder average the real robot computes, robot/units.py LegSpeed "encoder"), divided by
     a FIXED 120 rpm, plus a little noise for whole-degree encoder steps. v1 used the
     simulator's instantaneous speed, which the real hub cannot provide.
  6. TILT MARGIN: new penalty, 0 up to 40 deg body tilt (the normal gait rocks to ~34 deg),
     rising linearly to -1 per second at 70 deg; FLIP penalty 75 -> 100 so flipping still
     never pays: worst continuing second = 0 - 2.0 (heading) - 0.4 (drift) - 0.16 (jerk)
     - 1.0 (tilt) = -3.56, a whole 20 s episode at worst -71.2 > -100.
  7. RANDOM PUSHES every 3-6 s: a sudden extra spin of up to +/-5 rad/s about each of the
     world's two horizontal axes (the robot faces a random direction, so this covers every
     tilt direction). FakeRobot tests: the walking robot needs a 15-20 rad/s front-back
     (pitch) kick to tip, and sideways kicks up to 20 rad/s never tipped it, so these are
     about a third of a tipping kick: practice at recovering.
  The critic (training only) additionally sees the robot's top speed.
"""

import math
from dataclasses import dataclass

import torch

from mjlab.actuator.builtin_actuator import BuiltinVelocityActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.envs import ManagerBasedRlEnv, ManagerBasedRlEnvCfg
from mjlab.envs.mdp import (
    bad_orientation, base_ang_vel, base_lin_vel, projected_gravity, time_out,
)
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.events import push_by_setting_velocity, resolve_env_ids
from mjlab.managers.event_manager import EventTermCfg, RecomputeLevel, requires_model_fields
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.registry import register_mjlab_task
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import GaussianNoiseCfg

import walk_straight_task as V1
from robot_spec import S, make_robot_spec

TASK_ID = "HW8-SillyWalker-WalkStraight-v2"

# ============================================================== numbers (v1 values reused
# unless listed here)
TIMESTEP, DECISION_DT, EPISODE_S, NUM_ENVS = V1.TIMESTEP, V1.DECISION_DT, V1.EPISODE_S, 256
MAX_SPEED_RPM = 120.0                  # nominal top speed: only for the leg-speed scale and printouts
TOP_SPEED_RPM = (80.0, 140.0)          # [3] per robot
MASS_SCALE = (0.6, 1.6)                # [4]
ARMATURE_NOMINAL = 2e-4                # [1] kg m^2
ARMATURE = (5e-5, 5e-4)                # [1] log-uniform per leg
JOINT_FRICTION_SCALE = (0.5, 2.5)      # [2] x the 0.002 N m default, per leg
CONTACT_TIMECONST = (0.004, 0.008)     # [2] s, robot shapes, per robot
LEG_SPEED_NORM = MAX_SPEED_RPM * 2 * math.pi / 60      # [5] fixed scale (rad/s)
LEG_SPEED_NOISE = 0.02                 # [5] of 120 rpm: whole-degree encoder steps over 0.05 s
TILT_FREE, TILT_RANGE, W_TILT = math.radians(40), math.radians(30), 1.0   # [6]
FLIP_PENALTY = 100.0                   # [6]
PUSH_INTERVAL_S = (3.0, 6.0)           # [7]
PUSH_SPIN = {"roll": (-5.0, 5.0), "pitch": (-5.0, 5.0)}   # [7] rad/s about world x / y
ROBOT = V1.ROBOT
JOINTS = V1.JOINTS


def _state(env: ManagerBasedRlEnv) -> dict:
    """v1's per-robot memory plus v2's: the leg angles at the last decision (for the
    encoder-average leg speed) and this robot's motor top speed."""
    st = V1._state(env)
    n, d = env.num_envs, env.device
    st.setdefault("q_prev", torch.zeros(n, 2, device=d))
    st.setdefault("top_rpm", torch.full((n,), MAX_SPEED_RPM, device=d))
    return st


# ============================================================== action [3] [5]
class TopSpeedFractionAction(V1.UprightLegSpeedAction):
    """a (-1..1 per leg) -> fraction (a + 1) / 2 of this robot's top speed, upright direction.
    Also remembers the leg angles at this decision, for the encoder-average leg speed."""

    def __init__(self, cfg, env):
        super().__init__(cfg=cfg, env=env)
        self._env = env

    def process_actions(self, actions: torch.Tensor):
        self._raw_actions[:] = actions
        st = _state(self._env)
        st["q_prev"][:] = self._env.scene["robot"].data.joint_pos[:, ROBOT.joint_ids]
        top = (st["top_rpm"] * 2 * math.pi / 60).unsqueeze(-1)
        self._processed_actions = -top * (actions.clamp(-1.0, 1.0) + 1.0) / 2.0 * self.motor_scale

    def reset(self, env_ids=None):
        super().reset(env_ids)                                    # new per-side speed factors
        ids = slice(None) if env_ids is None else env_ids
        st = _state(self._env)
        n = st["top_rpm"][ids].shape[0]
        st["top_rpm"][ids] = torch.empty(n, device=self.device).uniform_(*TOP_SPEED_RPM)


@dataclass(kw_only=True)
class TopSpeedFractionActionCfg(V1.UprightLegSpeedActionCfg):
    def build(self, env):
        return TopSpeedFractionAction(self, env)


# ============================================================== observations [5]
def leg_speed_obs(env: ManagerBasedRlEnv) -> torch.Tensor:
    """How far each leg turned during the last decision / 0.05 s, / 120 rpm, + noise. [n, 2]"""
    q = env.scene["robot"].data.joint_pos[:, ROBOT.joint_ids]
    v = (q - _state(env)["q_prev"]) / DECISION_DT / LEG_SPEED_NORM
    return v + LEG_SPEED_NOISE * torch.randn_like(v)


def true_leg_speed(env):  # critic: the true instantaneous speed, same scale
    return env.scene["robot"].data.joint_vel[:, ROBOT.joint_ids] / LEG_SPEED_NORM


def top_speed_obs(env):   # critic only
    return (_state(env)["top_rpm"] / MAX_SPEED_RPM).unsqueeze(-1)


# ============================================================== rewards [6]
def r_tilt(env):
    """0 up to 40 deg of body tilt, rising to 1 at 70 deg (MJLab multiplies by dt)."""
    g = env.scene["robot"].data.projected_gravity_b
    tilt = torch.acos((-g[:, 2]).clamp(-1.0, 1.0))
    return ((tilt - TILT_FREE) / TILT_RANGE).clamp(0.0, 1.0)


# ============================================================== events
def reset_robot(env, env_ids, legs_in_step: bool = False):
    """v1's reset, then: leg speed starts at 0 (q_prev = the new leg angles)."""
    V1.reset_robot(env, env_ids, legs_in_step)
    ids = resolve_env_ids(env, env_ids)
    _state(env)["q_prev"][ids] = env.scene["robot"].data.joint_pos[ids][:, ROBOT.joint_ids]


@requires_model_fields("geom_solref", recompute=RecomputeLevel.none)
def contact_stiffness(env, env_ids, timeconst_range, asset_cfg: SceneEntityCfg):
    """Per robot, one random contact time constant for all its collision shapes [2]."""
    env_ids = resolve_env_ids(env, env_ids).to(env.device)
    geom_ids = env.scene[asset_cfg.name].indexing.geom_ids[asset_cfg.geom_ids]   # as MJLab's dr does
    tc = torch.empty(len(env_ids), device=env.device).uniform_(*timeconst_range)
    sr = env.sim.model.geom_solref
    sr[env_ids[:, None], geom_ids[None, :], 0] = tc[:, None]


# ============================================================== environment config
def make_env_cfg(num_envs: int = NUM_ENVS, timestep: float = TIMESTEP,
                 episode_s: float = EPISODE_S) -> ManagerBasedRlEnvCfg:
    robot = EntityCfg(
        spec_fn=lambda: make_robot_spec(max(0.002, 2 * timestep)),
        articulation=EntityArticulationInfoCfg(actuators=(
            BuiltinVelocityActuatorCfg(
                target_names_expr=JOINTS,
                damping=S.MOTOR_KV, effort_limit=S.MOTOR_MAX_TORQUE,
                armature=ARMATURE_NOMINAL, frictionloss=S.JOINT_FRICTION,
                delay_min_lag=V1.COMMAND_DELAY_STEPS[0], delay_max_lag=V1.COMMAND_DELAY_STEPS[1],
                delay_hold_prob=0.95,
            ),
        )),
        init_state=EntityCfg.InitialStateCfg(pos=(0.0, 0.0, 0.017)),
    )
    noise = lambda std: GaussianNoiseCfg(std=std)
    actor = {
        "tilt": ObservationTermCfg(func=projected_gravity, noise=noise(V1.TILT_NOISE)),
        "gyro": ObservationTermCfg(func=base_ang_vel, noise=noise(V1.GYRO_NOISE)),
        "heading": ObservationTermCfg(func=V1.heading_obs),
        "leg_angle": ObservationTermCfg(func=V1.leg_angle_obs),
        "leg_speed": ObservationTermCfg(func=leg_speed_obs),
        "last_command": ObservationTermCfg(func=V1.last_command),
    }
    critic = {
        "tilt": ObservationTermCfg(func=projected_gravity),
        "gyro": ObservationTermCfg(func=base_ang_vel),
        "heading": ObservationTermCfg(func=V1.true_heading),
        "leg_angle": ObservationTermCfg(func=V1.true_leg_angle),
        "leg_speed": ObservationTermCfg(func=true_leg_speed),
        "last_command": ObservationTermCfg(func=V1.last_command),
        "body_velocity": ObservationTermCfg(func=base_lin_vel),
        "sideways": ObservationTermCfg(func=V1.sideways_obs),
        "top_speed": ObservationTermCfg(func=top_speed_obs),
    }
    legs = SceneEntityCfg("robot", joint_names=JOINTS)
    robot_geoms = SceneEntityCfg("robot", geom_names=("body_box", "hub_right", "hub_left",
                                                      "leg_right_box", "leg_left_box"))
    events = {
        "reset_robot": EventTermCfg(func=reset_robot, mode="reset"),
        "friction_right_leg": EventTermCfg(func=dr.geom_friction, mode="reset", params={
            "ranges": V1.FRICTION, "asset_cfg": SceneEntityCfg("robot", geom_names=("leg_right_box",))}),
        "friction_left_leg": EventTermCfg(func=dr.geom_friction, mode="reset", params={
            "ranges": V1.FRICTION, "asset_cfg": SceneEntityCfg("robot", geom_names=("leg_left_box",))}),
        "friction_body": EventTermCfg(func=dr.geom_friction, mode="reset", params={
            "ranges": V1.FRICTION, "shared_random": True,
            "asset_cfg": SceneEntityCfg("robot", geom_names=("body_box", "hub_right", "hub_left"))}),
        "mass": EventTermCfg(func=dr.pseudo_inertia, mode="reset", params={
            "alpha_range": (math.log(MASS_SCALE[0]) / 2, math.log(MASS_SCALE[1]) / 2),
            "asset_cfg": SceneEntityCfg("robot", body_names=("body",))}),
        "com_shift": EventTermCfg(func=dr.body_com_offset, mode="reset", params={
            "ranges": {0: (-V1.COM_SHIFT_X, V1.COM_SHIFT_X)},
            "asset_cfg": SceneEntityCfg("robot", body_names=("body",))}),
        "motor_strength": EventTermCfg(func=V1.motor_strength, mode="reset", params={
            "scale_range": V1.MOTOR_STRENGTH_SCALE}),
        "armature": EventTermCfg(func=dr.joint_armature, mode="reset", params={
            "ranges": ARMATURE, "distribution": "log_uniform", "asset_cfg": legs}),
        "joint_friction": EventTermCfg(func=dr.joint_friction, mode="reset", params={
            "ranges": JOINT_FRICTION_SCALE, "operation": "scale", "asset_cfg": legs}),
        "contact_stiffness": EventTermCfg(func=contact_stiffness, mode="reset", params={
            "timeconst_range": CONTACT_TIMECONST, "asset_cfg": robot_geoms}),
        "push": EventTermCfg(func=push_by_setting_velocity, mode="interval",
                             interval_range_s=PUSH_INTERVAL_S, params={"velocity_range": PUSH_SPIN}),
    }
    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": robot}, num_envs=num_envs, env_spacing=1.5),
        observations={"actor": ObservationGroupCfg(actor, enable_corruption=True),
                      "critic": ObservationGroupCfg(critic, enable_corruption=False)},
        actions={"leg_speed": TopSpeedFractionActionCfg(
            entity_name="robot", actuator_names=JOINTS, use_default_offset=False)},
        events=events,
        rewards={
            "forward": RewardTermCfg(func=V1.r_forward, weight=V1.W_FORWARD),
            "heading": RewardTermCfg(func=V1.r_heading, weight=-V1.W_HEADING),
            "drift": RewardTermCfg(func=V1.r_drift, weight=-V1.W_DRIFT),
            "jerk": RewardTermCfg(func=V1.r_jerk, weight=-V1.W_JERK),
            "tilt": RewardTermCfg(func=r_tilt, weight=-W_TILT),
            "flip": RewardTermCfg(func=V1.r_flip, weight=-FLIP_PENALTY),
        },
        terminations={
            "time_out": TerminationTermCfg(func=time_out, time_out=True),
            "flipped": TerminationTermCfg(func=bad_orientation, params={"limit_angle": V1.FLIP_ANGLE}),
        },
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=timestep, cone="elliptic",
                                           iterations=20, ls_iterations=10)),
        decimation=round(DECISION_DT / timestep),
        episode_length_s=episode_s,
    )


def ppo_cfg(max_iterations: int = 800):
    cfg = V1.ppo_cfg(max_iterations)
    cfg.experiment_name = "walk_straight_v2"
    return cfg


def register(num_envs: int = NUM_ENVS, timestep: float = TIMESTEP, max_iterations: int = 800) -> str:
    register_mjlab_task(task_id=TASK_ID, env_cfg=make_env_cfg(num_envs, timestep),
                        play_env_cfg=make_env_cfg(1, timestep), rl_cfg=ppo_cfg(max_iterations))
    return TASK_ID
