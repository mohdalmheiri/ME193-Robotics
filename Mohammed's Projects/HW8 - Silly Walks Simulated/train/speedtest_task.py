"""
A MINIMAL MJLab task for the HW8 robot. For the speed test only, not the final design.

An MJLab "task" bundles everything the trainer needs:
  - scene:        the robot (robot_spec.py) on a flat floor, copied num_envs times
                  so many robots are simulated side by side
  - actions:      what the policy controls. Here: a speed target for each leg motor.
                  The policy outputs numbers around -1..1, scaled to +/-ACTION_SCALE rad/s.
  - motors:       MuJoCo velocity motors (cruise control), same numbers as sim/settings.py
  - observations: what the policy sees each step: body velocity and spin, which way
                  is down (gravity in the body frame, i.e. tilt), each leg's angle
                  (as sin/cos, because the legs spin all the way round) and speed,
                  and its own previous action
  - reward:       PLACEHOLDER: the body's speed toward +Y (the leg tips). It's only here
                  so training has something to optimise while we time it.
  - terminations: an episode ends after EPISODE_S seconds, or early if the body tilts
                  past 70 degrees (it is flipping over)
  - resets:       random leg angles and a small random heading at each episode start,
                  with the body lifted so no leg starts buried in the table
  - PPO settings: network sizes and learning settings (copied from MJLab's cartpole
                  example, which is also a small problem)

make_env_cfg(timestep) lets the speed test try different physics step sizes.
"""

import math

import torch

from mjlab.actuator.builtin_actuator import BuiltinVelocityActuatorCfg
from mjlab.entity import Entity, EntityArticulationInfoCfg, EntityCfg
from mjlab.envs import ManagerBasedRlEnv, ManagerBasedRlEnvCfg
from mjlab.envs.mdp import (
    bad_orientation, base_ang_vel, base_lin_vel, joint_vel_rel, last_action,
    projected_gravity, time_out,
)
from mjlab.envs.mdp.events import resolve_env_ids
from mjlab.envs.mdp.actions import JointVelocityActionCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.registry import register_mjlab_task
from mjlab.terrains import TerrainEntityCfg

from robot_spec import S, leg_box_extent, make_robot_spec

TASK_ID = "HW8-SillyWalker-SpeedTest"
CONTROL_DT = 0.02           # the policy acts 50 times per second
EPISODE_S = 10.0            # seconds per episode
ACTION_SCALE = 2 * S.MOTOR_SPEED    # policy output 1.0 = 120 rpm (S.MOTOR_SPEED is 60 rpm)
JOINTS = ("right", "left")
LEG_ALONG_LO, LEG_ALONG_HI, LEG_ACROSS_LO, LEG_ACROSS_HI = leg_box_extent()
ROBOT = SceneEntityCfg("robot", joint_names=JOINTS)


# ----------------------------------------------------------------- custom terms
def leg_angle_sin_cos(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = ROBOT) -> torch.Tensor:
    """sin and cos of each leg angle. Shape [num_envs, 4]. Spinning legs wrap around,
    so 359 deg and 1 deg should look alike; sin/cos does that, a raw angle doesn't."""
    q = env.scene[asset_cfg.name].data.joint_pos[:, asset_cfg.joint_ids]
    return torch.cat([torch.sin(q), torch.cos(q)], dim=-1)


def forward_speed(env: ManagerBasedRlEnv) -> torch.Tensor:
    """PLACEHOLDER reward: world-frame speed toward +Y (m/s). Shape [num_envs]."""
    robot: Entity = env.scene["robot"]
    return robot.data.root_link_lin_vel_w[:, 1]


def reset_robot_clear_of_table(env: ManagerBasedRlEnv, env_ids: torch.Tensor | None,
                               leg_range=(-math.pi, math.pi), yaw_range=(-0.2, 0.2),
                               asset_cfg: SceneEntityCfg = ROBOT) -> None:
    """Reset event: random leg angles and heading, body lifted clear of the table.

    Why: a leg pointing down reaches 48 mm below the axle, but the table is only 15 mm
    below it. Starting a robot with a leg inside the table makes the contact solver
    shove it out violently (robots were launched 0.2-0.8 m into the air). So for each
    robot we find the lowest point of either leg box at its new angles:
        lowest = min over the box's 4 corners of  along*sin(q) + across*cos(q)
    and put the axle at  max(body half-height, -lowest) + DROP_HEIGHT  above the table.
    The robot then drops a couple of millimetres onto the table and starts walking.
    """
    env_ids = resolve_env_ids(env, env_ids)
    n, dev = len(env_ids), env.device
    robot: Entity = env.scene[asset_cfg.name]

    q = torch.empty(n, 2, device=dev).uniform_(*leg_range)            # leg angles
    corners = [(a, b) for a in (LEG_ALONG_LO, LEG_ALONG_HI) for b in (LEG_ACROSS_LO, LEG_ACROSS_HI)]
    lowest = torch.stack([a * torch.sin(q) + b * torch.cos(q) for a, b in corners]).amin(dim=(0, 2))
    axle_z = torch.clamp(-lowest, min=S.TABLE_HEIGHT_BELOW_AXLE) + S.DROP_HEIGHT

    yaw = torch.empty(n, device=dev).uniform_(*yaw_range)
    pose = torch.zeros(n, 7, device=dev)
    pose[:, :3] = env.scene.env_origins[env_ids]
    pose[:, 2] += axle_z
    pose[:, 3] = torch.cos(yaw / 2)                                   # quaternion w
    pose[:, 6] = torch.sin(yaw / 2)                                   # quaternion z
    robot.write_root_link_pose_to_sim(pose, env_ids=env_ids)
    robot.write_root_link_velocity_to_sim(torch.zeros(n, 6, device=dev), env_ids=env_ids)
    joint_ids = torch.tensor(asset_cfg.joint_ids, device=dev) if isinstance(asset_cfg.joint_ids, list) else asset_cfg.joint_ids
    robot.write_joint_state_to_sim(q, torch.zeros_like(q), env_ids=env_ids, joint_ids=joint_ids)


# ----------------------------------------------------------------- environment
def make_env_cfg(timestep: float = 0.002, num_envs: int = 256) -> ManagerBasedRlEnvCfg:
    contact_timeconst = max(0.002, 2 * timestep)    # stability rule: >= 2 physics steps
    robot = EntityCfg(
        spec_fn=lambda: make_robot_spec(contact_timeconst),
        articulation=EntityArticulationInfoCfg(actuators=(
            BuiltinVelocityActuatorCfg(
                target_names_expr=JOINTS,
                damping=S.MOTOR_KV,                 # velocity-motor gain (MuJoCo's kv)
                effort_limit=S.MOTOR_MAX_TORQUE,
                armature=S.JOINT_ARMATURE,
                frictionloss=S.JOINT_FRICTION,
            ),
        )),
        init_state=EntityCfg.InitialStateCfg(
            pos=(0.0, 0.0, S.TABLE_HEIGHT_BELOW_AXLE + S.DROP_HEIGHT),
            joint_pos={".*": 0.0}, joint_vel={".*": 0.0},
        ),
    )
    actor_terms = {
        "lin_vel": ObservationTermCfg(func=base_lin_vel),
        "ang_vel": ObservationTermCfg(func=base_ang_vel),
        "gravity": ObservationTermCfg(func=projected_gravity),
        "leg_angle": ObservationTermCfg(func=leg_angle_sin_cos),
        "leg_vel": ObservationTermCfg(func=joint_vel_rel, params={"asset_cfg": ROBOT}),
        "last_action": ObservationTermCfg(func=last_action),
    }
    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": robot}, num_envs=num_envs, env_spacing=0.5),
        observations={"actor": ObservationGroupCfg(actor_terms),
                      "critic": ObservationGroupCfg({**actor_terms})},
        actions={"leg_speed": JointVelocityActionCfg(
            entity_name="robot", actuator_names=JOINTS, scale=ACTION_SCALE,
            use_default_offset=False)},
        events={"reset_robot": EventTermCfg(func=reset_robot_clear_of_table, mode="reset")},
        rewards={"forward": RewardTermCfg(func=forward_speed, weight=1.0)},
        terminations={
            "time_out": TerminationTermCfg(func=time_out, time_out=True),
            "flipping": TerminationTermCfg(func=bad_orientation,
                                           params={"limit_angle": math.radians(70)}),
        },
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=timestep)),
        decimation=round(CONTROL_DT / timestep),   # physics steps per policy step
        episode_length_s=EPISODE_S,
    )


def ppo_cfg() -> RslRlOnPolicyRunnerCfg:
    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(hidden_dims=(64, 64), activation="elu", obs_normalization=True,
                            distribution_cfg={"class_name": "GaussianDistribution",
                                              "init_std": 1.0, "std_type": "scalar"}),
        critic=RslRlModelCfg(hidden_dims=(64, 64), activation="elu", obs_normalization=True),
        algorithm=RslRlPpoAlgorithmCfg(
            value_loss_coef=1.0, use_clipped_value_loss=True, clip_param=0.2,
            entropy_coef=0.01, num_learning_epochs=5, num_mini_batches=4,
            learning_rate=1.0e-3, schedule="adaptive", gamma=0.99, lam=0.95,
            desired_kl=0.01, max_grad_norm=1.0),
        experiment_name="silly_walker_speedtest",
        logger="tensorboard",        # local files only, no Weights & Biases account
        upload_model=False,
        save_interval=50,
        num_steps_per_env=24,        # each robot takes 24 policy steps per training round
        max_iterations=10,
    )


def register(timestep: float = 0.002, num_envs: int = 256) -> str:
    register_mjlab_task(task_id=TASK_ID, env_cfg=make_env_cfg(timestep, num_envs),
                        play_env_cfg=make_env_cfg(timestep, 1), rl_cfg=ppo_cfg())
    return TASK_ID
