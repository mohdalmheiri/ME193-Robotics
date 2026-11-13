"""
The real HW8 training task: make a lopsided Silly Walker walk STRAIGHT.

The pieces, and how each works:

  ROBOTS      robot_spec.py's model on a flat table, NUM_ENVS copies side by side.

  DECISIONS   20 per second (DECISION_DT = 0.05 s). The real robot's motion sensor
              delivered a new reading only every ~31 ms in MT1's recordings, so 50 per
              second (0.02 s) would be faster than the real robot can see.

  ACTIONS     Two numbers from the policy, one per leg, clipped to -1..1 and mapped to
              a speed in the "walks upright" direction only:
                  -1 -> leg stopped,  +1 -> full speed (MAX_SPEED_RPM)
              (In our coordinates the upright gait is a NEGATIVE joint speed.)
              Each robot's two motors also get their own random "strength of speed"
              (MOTOR_SPEED_SCALE), so equal commands don't give equal speeds - the
              main reason a real robot drifts.

  INPUTS      Only what the real Double Motor can measure, with realistic noise:
   (actor)      - tilt: which way gravity points in the body frame   (pitch/roll)
                - turning rate around 3 axes                        (gyroscope)
                - heading relative to the start, as sin/cos         (yaw, reset to 0
                  at the start; with a slow random drift, like a real gyro yaw)
                - each leg's angle as sin/cos                       (absolute encoders,
                  with a small random calibration error per leg)
                - each leg's speed                                  (motor speed report)
                - the previous command                              (the laptop knows it)
              NOT position or speed across the table: no sensor measures those.
   (critic)   The critic (PPO's "how good is this situation" network) is only used
              during training, so it may also see true values the robot can't measure:
              body speed across the table, sideways offset and true heading. This
              makes learning faster without making the final policy rely on them.

  REWARD      Per second of walking (MJLab multiplies by the time step):
                forward   +1.0 x speed along the start direction / 30 mm/s,
                          clipped to 0..1.5            (bonus for progress, capped)
                heading   -1.0 x |heading error| / 10 deg, capped at -2.0
                          (the MAIN straightness term: the robot can sense it)
                drift     -0.2 x |sideways offset| / 3 cm, capped at -0.4
                          (light tie-breaker: the robot can't sense it)
                jerk      -0.02 x sum of (command change)^2, at most -0.16
              plus a one-time FLIP penalty of -75 when the body tilts past 70 deg,
              which also ends the episode.
              Why flipping can never pay: the worst a robot can score per second
              while continuing is 0 - 2.0 - 0.4 - 0.16 = -2.56, so even a whole
              20 s episode can lose at most -51.2. Flipping costs -75, always worse.

  RANDOMIZED  At every reset, each robot gets its own (see the ranges below):
              motor speed and strength per side, friction per leg and for the body,
              body mass, left/right center of mass, starting leg angles and heading,
              command delay, sensor noise, gyro drift, encoder calibration error.

  ENDINGS     After EPISODE_S seconds, or early if the body tilts past 70 deg.
"""

import math
from dataclasses import dataclass

import torch

from mjlab.actuator.builtin_actuator import BuiltinVelocityActuatorCfg
from mjlab.entity import Entity, EntityArticulationInfoCfg, EntityCfg
from mjlab.envs import ManagerBasedRlEnv, ManagerBasedRlEnvCfg
from mjlab.envs.mdp import (
    bad_orientation, base_ang_vel, base_lin_vel, projected_gravity, time_out,
)
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointVelocityActionCfg
from mjlab.envs.mdp.actions.actions import JointVelocityAction
from mjlab.envs.mdp.events import resolve_env_ids
from mjlab.managers.event_manager import EventTermCfg, RecomputeLevel, requires_model_fields
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.registry import register_mjlab_task
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import GaussianNoiseCfg

from robot_spec import S, leg_box_extent, make_robot_spec

TASK_ID = "HW8-SillyWalker-WalkStraight"

# ============================================================== tunable numbers
TIMESTEP = 0.002              # physics step (s); contact stiffness = 2 x TIMESTEP
DECISION_DT = 0.05            # policy decides 20 times per second
EPISODE_S = 20.0              # seconds per episode (about 50 cm of walking)
NUM_ENVS = 512                # robots simulated side by side
MAX_SPEED_RPM = 120.0         # leg speed at full command (2x the 60 rpm guess; MEASURE)

# Reward (all per second, see the module docstring)
W_FORWARD, V_REF, FORWARD_CAP = 1.0, 0.030, 1.5     # weight, m/s for "1", cap
W_HEADING, HEADING_REF, HEADING_CAP = 1.0, math.radians(10), 2.0
W_DRIFT, DRIFT_REF, DRIFT_CAP = 0.2, 0.03, 2.0
W_JERK = 0.02
FLIP_PENALTY = 75.0           # one-time; must exceed the worst continuing loss (51.2)
FLIP_ANGLE = math.radians(70)

# Left/right differences, sampled per robot at every reset (to be matched to the
# real robot's measured drift)
MOTOR_SPEED_SCALE = (0.90, 1.10)    # each side's speed for the same command
MOTOR_STRENGTH_SCALE = (0.8, 1.2)   # each side's torque limit
FRICTION = (0.4, 0.9)               # each leg and the body, separately
MASS_SCALE = (0.8, 1.3)             # body mass x (80-130 g)
COM_SHIFT_X = 0.003                 # center of mass shifted left/right by up to 3 mm
COMMAND_DELAY_STEPS = (0, 20)       # 0-40 ms Bluetooth delay, in physics steps
# Sensor imperfections (actor only)
TILT_NOISE = 0.035                  # ~2 deg, on the gravity direction
GYRO_NOISE = math.radians(3)        # rad/s
HEADING_NOISE = math.radians(1)
HEADING_DRIFT = math.radians(0.5)   # up to 0.5 deg/s of yaw drift, random per robot
LEG_ANGLE_NOISE = math.radians(2)
LEG_CALIB_ERROR = math.radians(2)   # per leg, fixed for the episode
LEG_SPEED_NOISE = 0.05              # +/- 5 %

# ============================================================== helpers
JOINTS = ("right", "left")
ROBOT = SceneEntityCfg("robot", joint_names=JOINTS)
MAX_SPEED = MAX_SPEED_RPM * 2 * math.pi / 60
LEG_ALONG_LO, LEG_ALONG_HI, LEG_ACROSS_LO, LEG_ACROSS_HI = leg_box_extent()


def _state(env: ManagerBasedRlEnv) -> dict:
    """Per-robot values remembered across one episode (start pose, sensor errors).

    Stored on the env object; created on first use. Reward terms need the start
    position and heading, which only the reset event knows.
    """
    if not hasattr(env, "_hw8"):
        n, d = env.num_envs, env.device
        env._hw8 = {
            "start_xy": torch.zeros(n, 2, device=d),
            "start_yaw": torch.zeros(n, device=d),
            "yaw_drift": torch.zeros(n, device=d),     # rad/s
            "leg_calib": torch.zeros(n, 2, device=d),  # rad
        }
    return env._hw8


def body_yaw(robot: Entity) -> torch.Tensor:
    """Heading of the robot's front (+Y body axis) on the table, in radians.

    Rotates the body's +Y axis into the world with the root quaternion (w, x, y, z)
    and takes the angle of its table-plane projection; 0 = facing world +Y.
    """
    w, x, y, z = robot.data.root_link_quat_w.unbind(-1)
    front_x = 2 * (x * y - w * z)          # world x of body +Y axis
    front_y = 1 - 2 * (x * x + z * z)      # world y of body +Y axis
    return torch.atan2(-front_x, front_y)


def wrap(a: torch.Tensor) -> torch.Tensor:
    """Wrap angles to -pi..pi."""
    return torch.atan2(torch.sin(a), torch.cos(a))


def heading_error(env: ManagerBasedRlEnv) -> torch.Tensor:
    return wrap(body_yaw(env.scene["robot"]) - _state(env)["start_yaw"])


def track_frame(env: ManagerBasedRlEnv):
    """Unit vectors along the start direction ("forward") and to its right."""
    yaw0 = _state(env)["start_yaw"]
    fwd = torch.stack([-torch.sin(yaw0), torch.cos(yaw0)], -1)
    right = torch.stack([torch.cos(yaw0), torch.sin(yaw0)], -1)
    return fwd, right


def sideways_offset(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Distance (m) from the start line, + = to the right."""
    robot = env.scene["robot"]
    rel = robot.data.root_link_pos_w[:, :2] - _state(env)["start_xy"]
    return (rel * track_frame(env)[1]).sum(-1)


def forward_speed(env: ManagerBasedRlEnv) -> torch.Tensor:
    robot = env.scene["robot"]
    return (robot.data.root_link_lin_vel_w[:, :2] * track_frame(env)[0]).sum(-1)


# ============================================================== actions
class UprightLegSpeedAction(JointVelocityAction):
    """Policy output (-1..1 per leg) -> leg speed in the upright-walking direction.

    target speed = -MAX_SPEED * (a + 1) / 2 * motor_scale
    where a is clipped to -1..1 and motor_scale is this robot's random speed factor
    for that side (resampled at every reset).
    """

    def __init__(self, cfg, env):
        super().__init__(cfg=cfg, env=env)
        self.motor_scale = torch.ones(self.num_envs, self.action_dim, device=self.device)

    def process_actions(self, actions: torch.Tensor):
        self._raw_actions[:] = actions
        a = actions.clamp(-1.0, 1.0)
        self._processed_actions = -MAX_SPEED * (a + 1.0) / 2.0 * self.motor_scale

    def reset(self, env_ids=None):
        super().reset(env_ids)
        ids = slice(None) if env_ids is None else env_ids
        n = self.motor_scale[ids].shape[0]
        self.motor_scale[ids] = torch.empty(n, self.action_dim, device=self.device).uniform_(
            *MOTOR_SPEED_SCALE)


@dataclass(kw_only=True)
class UprightLegSpeedActionCfg(JointVelocityActionCfg):
    def build(self, env):
        return UprightLegSpeedAction(self, env)


# ============================================================== observations
def heading_obs(env: ManagerBasedRlEnv) -> torch.Tensor:
    """What the IMU yaw would say: true heading error + slow drift + noise. [n, 2]"""
    st = _state(env)
    t = env.episode_length_buf.float() * env.step_dt
    h = heading_error(env) + st["yaw_drift"] * t + HEADING_NOISE * torch.randn_like(t)
    return torch.stack([torch.sin(h), torch.cos(h)], -1)


def leg_angle_obs(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Encoder leg angles (+ calibration error + noise) as sin/cos. [n, 4]"""
    q = env.scene["robot"].data.joint_pos[:, ROBOT.joint_ids]
    q = q + _state(env)["leg_calib"] + LEG_ANGLE_NOISE * torch.randn_like(q)
    return torch.cat([torch.sin(q), torch.cos(q)], -1)


def leg_speed_obs(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Leg speeds with +/-5 % noise, scaled so full speed ~ 1. [n, 2]"""
    v = env.scene["robot"].data.joint_vel[:, ROBOT.joint_ids]
    return v * (1 + LEG_SPEED_NOISE * torch.randn_like(v)) / MAX_SPEED


def last_command(env: ManagerBasedRlEnv) -> torch.Tensor:
    return env.action_manager.action.clamp(-1.0, 1.0)


# critic-only (true values)
def true_heading(env):  return torch.stack([torch.sin(heading_error(env)), torch.cos(heading_error(env))], -1)
def true_leg_angle(env):
    q = env.scene["robot"].data.joint_pos[:, ROBOT.joint_ids]
    return torch.cat([torch.sin(q), torch.cos(q)], -1)
def true_leg_speed(env): return env.scene["robot"].data.joint_vel[:, ROBOT.joint_ids] / MAX_SPEED
def sideways_obs(env):   return (sideways_offset(env) / DRIFT_REF).unsqueeze(-1)


# ============================================================== rewards
def r_forward(env):
    return (forward_speed(env) / V_REF).clamp(0.0, FORWARD_CAP)


def r_heading(env):
    return (heading_error(env).abs() / HEADING_REF).clamp(max=HEADING_CAP)


def r_drift(env):
    return (sideways_offset(env).abs() / DRIFT_REF).clamp(max=DRIFT_CAP)


def r_jerk(env):
    """Sum of squared command changes, on clipped commands (so at most 2 x 2^2 = 8)."""
    am = env.action_manager
    return (am.action.clamp(-1, 1) - am.prev_action.clamp(-1, 1)).square().sum(-1)


def r_flip(env):
    """1/dt on the step a robot flips (MJLab multiplies by dt -> exactly 1 per flip)."""
    return env.termination_manager.terminated.float() / env.step_dt


# ============================================================== reset
def reset_robot(env: ManagerBasedRlEnv, env_ids: torch.Tensor | None,
                legs_in_step: bool = False) -> None:
    """Random leg angles and heading, body lifted clear of the table, and new
    per-robot sensor errors. Remembers the start pose for the reward.

    Height: a leg pointing down reaches 48 mm below the axle but the table is only
    15 mm below it, so we put the axle at max(15 mm, deepest leg corner) + 2 mm.
    Without this, robots started inside the table and were launched up to 0.8 m.

    The two legs normally start at independent random angles: legs out of step
    make even a perfectly matched robot turn (found by reward_check.py), and the
    real robot's leg phase changes whenever its motors run at different speeds.
    legs_in_step=True starts both legs at the same angle (used by the checks).
    """
    env_ids = resolve_env_ids(env, env_ids)
    n, dev = len(env_ids), env.device
    robot: Entity = env.scene["robot"]
    st = _state(env)

    q = torch.empty(n, 2, device=dev).uniform_(-math.pi, math.pi)
    if legs_in_step:
        q[:, 1] = q[:, 0]
    corners = [(a, b) for a in (LEG_ALONG_LO, LEG_ALONG_HI) for b in (LEG_ACROSS_LO, LEG_ACROSS_HI)]
    lowest = torch.stack([a * torch.sin(q) + b * torch.cos(q) for a, b in corners]).amin(dim=(0, 2))
    axle_z = torch.clamp(-lowest, min=S.TABLE_HEIGHT_BELOW_AXLE) + S.DROP_HEIGHT

    yaw = torch.empty(n, device=dev).uniform_(-math.pi, math.pi)   # any direction on the table
    pose = torch.zeros(n, 7, device=dev)
    pose[:, :3] = env.scene.env_origins[env_ids]
    pose[:, 2] += axle_z
    pose[:, 3], pose[:, 6] = torch.cos(yaw / 2), torch.sin(yaw / 2)
    robot.write_root_link_pose_to_sim(pose, env_ids=env_ids)
    robot.write_root_link_velocity_to_sim(torch.zeros(n, 6, device=dev), env_ids=env_ids)
    joint_ids = torch.tensor(ROBOT.joint_ids, device=dev) if isinstance(ROBOT.joint_ids, list) else ROBOT.joint_ids
    robot.write_joint_state_to_sim(q, torch.zeros_like(q), env_ids=env_ids, joint_ids=joint_ids)

    st["start_xy"][env_ids] = pose[:, :2]
    st["start_yaw"][env_ids] = yaw
    st["yaw_drift"][env_ids] = torch.empty(n, device=dev).uniform_(-HEADING_DRIFT, HEADING_DRIFT)
    st["leg_calib"][env_ids] = torch.empty(n, 2, device=dev).uniform_(-LEG_CALIB_ERROR, LEG_CALIB_ERROR)


@requires_model_fields("actuator_forcerange", recompute=RecomputeLevel.none)
def motor_strength(env: ManagerBasedRlEnv, env_ids: torch.Tensor | None,
                   scale_range: tuple[float, float]) -> None:
    """Give each motor of each robot its own torque limit: default x random scale.

    MJLab's built-in effort_limits() doesn't support velocity motors, so this does the
    same thing directly: the velocity motor's torque limit is its MuJoCo
    'actuator_forcerange', which the decorator above makes separate for every robot.
    """
    env_ids = resolve_env_ids(env, env_ids).to(env.device)
    ctrl_ids = env.scene["robot"].actuators[0].global_ctrl_ids
    default = env.sim.get_default_field("actuator_forcerange")
    scale = torch.empty(len(env_ids), len(ctrl_ids), device=env.device).uniform_(*scale_range)
    fr = env.sim.model.actuator_forcerange
    fr[env_ids[:, None], ctrl_ids, 0] = default[ctrl_ids, 0] * scale
    fr[env_ids[:, None], ctrl_ids, 1] = default[ctrl_ids, 1] * scale


# ============================================================== environment config
def make_env_cfg(num_envs: int = NUM_ENVS, timestep: float = TIMESTEP,
                 episode_s: float = EPISODE_S) -> ManagerBasedRlEnvCfg:
    robot = EntityCfg(
        spec_fn=lambda: make_robot_spec(max(0.002, 2 * timestep)),
        articulation=EntityArticulationInfoCfg(actuators=(
            BuiltinVelocityActuatorCfg(
                target_names_expr=JOINTS,
                damping=S.MOTOR_KV, effort_limit=S.MOTOR_MAX_TORQUE,
                armature=S.JOINT_ARMATURE, frictionloss=S.JOINT_FRICTION,
                delay_min_lag=COMMAND_DELAY_STEPS[0], delay_max_lag=COMMAND_DELAY_STEPS[1],
                delay_hold_prob=0.95,     # mostly a steady delay, occasionally changing
            ),
        )),
        init_state=EntityCfg.InitialStateCfg(pos=(0.0, 0.0, 0.017)),
    )
    noise = lambda std: GaussianNoiseCfg(std=std)
    actor = {
        "tilt": ObservationTermCfg(func=projected_gravity, noise=noise(TILT_NOISE)),
        "gyro": ObservationTermCfg(func=base_ang_vel, noise=noise(GYRO_NOISE)),
        "heading": ObservationTermCfg(func=heading_obs),
        "leg_angle": ObservationTermCfg(func=leg_angle_obs),
        "leg_speed": ObservationTermCfg(func=leg_speed_obs),
        "last_command": ObservationTermCfg(func=last_command),
    }
    critic = {
        "tilt": ObservationTermCfg(func=projected_gravity),
        "gyro": ObservationTermCfg(func=base_ang_vel),
        "heading": ObservationTermCfg(func=true_heading),
        "leg_angle": ObservationTermCfg(func=true_leg_angle),
        "leg_speed": ObservationTermCfg(func=true_leg_speed),
        "last_command": ObservationTermCfg(func=last_command),
        "body_velocity": ObservationTermCfg(func=base_lin_vel),      # privileged
        "sideways": ObservationTermCfg(func=sideways_obs),            # privileged
    }
    events = {
        "reset_robot": EventTermCfg(func=reset_robot, mode="reset"),
        "friction_right_leg": EventTermCfg(func=dr.geom_friction, mode="reset", params={
            "ranges": FRICTION, "asset_cfg": SceneEntityCfg("robot", geom_names=("leg_right_box",))}),
        "friction_left_leg": EventTermCfg(func=dr.geom_friction, mode="reset", params={
            "ranges": FRICTION, "asset_cfg": SceneEntityCfg("robot", geom_names=("leg_left_box",))}),
        "friction_body": EventTermCfg(func=dr.geom_friction, mode="reset", params={
            "ranges": FRICTION, "shared_random": True,
            "asset_cfg": SceneEntityCfg("robot", geom_names=("body_box", "hub_right", "hub_left"))}),
        "mass": EventTermCfg(func=dr.pseudo_inertia, mode="reset", params={
            # mass and inertia scale together by e^(2 alpha)
            "alpha_range": (math.log(MASS_SCALE[0]) / 2, math.log(MASS_SCALE[1]) / 2),
            "asset_cfg": SceneEntityCfg("robot", body_names=("body",))}),
        "com_shift": EventTermCfg(func=dr.body_com_offset, mode="reset", params={
            "ranges": {0: (-COM_SHIFT_X, COM_SHIFT_X)},
            "asset_cfg": SceneEntityCfg("robot", body_names=("body",))}),
        "motor_strength": EventTermCfg(func=motor_strength, mode="reset", params={
            "scale_range": MOTOR_STRENGTH_SCALE}),
    }
    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": robot}, num_envs=num_envs, env_spacing=1.5),
        observations={"actor": ObservationGroupCfg(actor, enable_corruption=True),
                      "critic": ObservationGroupCfg(critic, enable_corruption=False)},
        actions={"leg_speed": UprightLegSpeedActionCfg(
            entity_name="robot", actuator_names=JOINTS, use_default_offset=False)},
        events=events,
        rewards={
            "forward": RewardTermCfg(func=r_forward, weight=W_FORWARD),
            "heading": RewardTermCfg(func=r_heading, weight=-W_HEADING),
            "drift": RewardTermCfg(func=r_drift, weight=-W_DRIFT),
            "jerk": RewardTermCfg(func=r_jerk, weight=-W_JERK),
            "flip": RewardTermCfg(func=r_flip, weight=-FLIP_PENALTY),
        },
        terminations={
            "time_out": TerminationTermCfg(func=time_out, time_out=True),
            "flipped": TerminationTermCfg(func=bad_orientation, params={"limit_angle": FLIP_ANGLE}),
        },
        # Friction: "elliptic" (the same in every direction, like real friction).
        # MJLab's default "pyramidal" approximation is tied to the world's x/y axes:
        # a perfect-twin robot facing 30-45 deg off an axis turned up to 35 deg in 10 s
        # purely from that. Elliptic gives 0.0 deg and matches plain MuJoCo's 310 mm
        # walk, but is ~5x slower; 20 solver iterations (instead of 100) gives the same
        # result and claws back ~30 % of the speed.
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=timestep, cone="elliptic",
                                           iterations=20, ls_iterations=10)),
        decimation=round(DECISION_DT / timestep),
        episode_length_s=episode_s,
    )


def ppo_cfg(max_iterations: int = 300) -> RslRlOnPolicyRunnerCfg:
    """PPO settings: two small networks (64-64) and standard learning settings."""
    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(hidden_dims=(64, 64), activation="elu", obs_normalization=True,
                            distribution_cfg={"class_name": "GaussianDistribution",
                                              "init_std": 0.5, "std_type": "scalar"}),
        critic=RslRlModelCfg(hidden_dims=(64, 64), activation="elu", obs_normalization=True),
        algorithm=RslRlPpoAlgorithmCfg(
            value_loss_coef=1.0, use_clipped_value_loss=True, clip_param=0.2,
            entropy_coef=0.005, num_learning_epochs=5, num_mini_batches=4,
            learning_rate=1.0e-3, schedule="adaptive", gamma=0.99, lam=0.95,
            desired_kl=0.01, max_grad_norm=1.0),
        experiment_name="walk_straight",
        logger="tensorboard", upload_model=False,
        save_interval=50, num_steps_per_env=24, max_iterations=max_iterations,
    )


def register(num_envs: int = NUM_ENVS, timestep: float = TIMESTEP, max_iterations: int = 300) -> str:
    register_mjlab_task(task_id=TASK_ID, env_cfg=make_env_cfg(num_envs, timestep),
                        play_env_cfg=make_env_cfg(1, timestep), rl_cfg=ppo_cfg(max_iterations))
    return TASK_ID
