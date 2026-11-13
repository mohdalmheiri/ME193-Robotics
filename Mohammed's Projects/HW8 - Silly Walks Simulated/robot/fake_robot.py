"""
FakeRobot: the training simulator pretending to be the LEGO Double Motor.

It answers through the same interface as RealRobot (robot_interface.py) and in the hub's
own units (milli-g, deg/s, degrees, encoder degrees, percent), so the control loop and
units.py are exercised exactly as on the real robot.

How it works
  Physics   robot/model/scene.xml, the exact model MJLab trains on (exported and checked
            field-by-field by train/export_policy.py): same robot, floor, motors, contact
            settings, ELLIPTIC friction, solver settings and 0.002 s step.
  Lopsided  At reset it draws one random robot from the training ranges
            (policy_meta.json "randomization"): each leg's friction and the body's,
            body mass, sideways center-of-mass shift, each motor's torque limit and speed
            factor, starting leg angles and heading.
  Motors    send(right %, left %) -> leg speed from the rpm-per-percent table in config.py
            (the fake hub behaves exactly as config.py says), times this robot's speed
            factor. Commands reach the motors after a random 0-40 ms Bluetooth delay that
            mostly holds steady (the same delay model MJLab trained with: each physics
            step keeps the delay with 95 % probability, otherwise draws a new one).
  Sensors   Every 31 ms (MT1's measured rate) the fake hub takes a "sensor message":
              accelerometer  milli-g, the real specific force (gravity + the body's own
                             acceleration, so it feels the gait's bumps like a real one)
              gyroscope      deg/s, rounded to whole numbers
              pitch/roll     from the body's tilt, using config.py's conventions
              yaw            heading change since connect(), plus a slow random drift
              encoders       absolute 0..359 deg (with a fixed per-leg calibration error)
                             and counted position, whole degrees
            with the same noise amounts as training (policy_meta.json "noise"), then
            rounded to whole numbers as the real hub reports them. read() returns the most
            recent message, like the real library.
  Clock     Simulated time. wait_until(t) runs the physics up to t; with realtime=True it
            also sleeps so 1 simulated second takes 1 real second.
  Test hooks (for the safety tests): disconnect(), freeze_sensors(), tip_over().
"""

import math
import time

import mujoco
import numpy as np

import config as C
import units as U
from robot_interface import MotorReading, Reading, RobotInterface

SENSOR_PERIOD_S = 0.031
JOINT = {"right": "robot/right", "left": "robot/left"}


class FakeRobot(RobotInterface):
    def __init__(self, seed: int = 0, realtime: bool = False, randomize: bool = True,
                 noise: bool = True, legs_in_step: bool = False, start_q=None,
                 start_yaw: float | None = None):
        self.rng = np.random.default_rng(seed)
        self.realtime, self.randomize, self.noise = realtime, randomize, noise
        self.m = mujoco.MjModel.from_xml_path(str(U.MODEL_DIR / "scene.xml"))
        self.d = mujoco.MjData(self.m)
        self.dt = self.m.opt.timestep
        self.body = self.m.body("robot/body").id
        self.qadr = {s: self.m.jnt_qposadr[self.m.joint(j).id] for s, j in JOINT.items()}
        self.vadr = {s: self.m.jnt_dofadr[self.m.joint(j).id] for s, j in JOINT.items()}
        self.act = {s: self.m.actuator(j).id for s, j in JOINT.items()}
        self._connected = False
        self._sensors_frozen = False
        self._tip_until = -1.0
        self._randomize_robot(legs_in_step, start_q, start_yaw)

    # ------------------------------------------------------------ one random robot
    def _randomize_robot(self, legs_in_step, start_q, start_yaw):
        m, rng, R, N = self.m, self.rng, U.META["randomization"], U.META["noise"]
        self.info = {}
        if self.randomize:
            for g in ("robot/leg_right_box", "robot/leg_left_box"):
                m.geom_friction[m.geom(g).id, 0] = self.info[g] = rng.uniform(*R["friction"])
            f_body = self.info["body_friction"] = rng.uniform(*R["friction"])
            for g in ("robot/body_box", "robot/hub_right", "robot/hub_left"):
                m.geom_friction[m.geom(g).id, 0] = f_body
            # mass and inertia scale together (MJLab pseudo_inertia with alpha only)
            lo, hi = (math.log(x) / 2 for x in R["mass_scale"])
            k = self.info["mass_scale"] = math.exp(2 * rng.uniform(lo, hi))
            m.body_mass[self.body] *= k
            m.body_inertia[self.body] *= k
            m.body_ipos[self.body, 0] += rng.uniform(-R["com_shift_x_m"], R["com_shift_x_m"])
            for s in ("right", "left"):
                m.actuator_forcerange[self.act[s]] *= rng.uniform(*R["motor_strength_scale"])
            mujoco.mj_setConst(m, self.d)     # recompute quantities that depend on mass
        self.motor_scale = {s: rng.uniform(*R["motor_speed_scale"]) if self.randomize else 1.0
                            for s in ("right", "left")}
        self.delay_range = R["command_delay_physics_steps"]
        self.hold_prob = R["command_delay_hold_prob"]
        self.lag = int(rng.integers(self.delay_range[0], self.delay_range[1] + 1))
        # sensor errors fixed for this robot (as in training's reset)
        self.yaw_drift = rng.uniform(-N["heading_drift_rad_s"], N["heading_drift_rad_s"]) if self.noise else 0.0
        self.leg_calib = {s: rng.uniform(-N["leg_calib_rad"], N["leg_calib_rad"]) if self.noise else 0.0
                          for s in ("right", "left")}

        # start pose: random leg angles, axle lifted above the lowest leg corner, any heading
        q = np.array(start_q) if start_q is not None else rng.uniform(-math.pi, math.pi, 2)
        if legs_in_step and start_q is None:
            q[1] = q[0]
        al_lo, al_hi, ac_lo, ac_hi = U.META["reset"]["leg_box_extent_m"]
        lowest = min(a * math.sin(qi) + b * math.cos(qi)
                     for a in (al_lo, al_hi) for b in (ac_lo, ac_hi) for qi in q)
        axle_z = max(-lowest, U.META["reset"]["table_height_below_axle_m"]) + U.META["reset"]["drop_height_m"]
        yaw = rng.uniform(-math.pi, math.pi) if start_yaw is None else start_yaw
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[:7] = [0, 0, axle_z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        self.d.qpos[self.qadr["right"]], self.d.qpos[self.qadr["left"]] = q
        mujoco.mj_forward(self.m, self.d)
        self.start_xy = self.d.qpos[:2].copy()
        self.start_yaw = yaw
        self.yaw_at_connect = yaw
        self.history = []                     # wanted joint speeds, one entry per physics step
        self.wanted = np.zeros(2)             # latest command, as target joint speeds (rad/s)
        self.next_sensor_t = 0.0
        self.count = 0
        self.last = None
        self.encoder_turns = {s: 0.0 for s in ("right", "left")}

    # ------------------------------------------------------------ truth (for checks only)
    def body_yaw(self) -> float:
        """Heading of the robot's front (+y body axis), CCW from world +y (as in training)."""
        w, x, y, z = self.d.xquat[self.body]
        return math.atan2(-2 * (x * y - w * z), 1 - 2 * (x * x + z * z))

    def truth(self) -> dict:
        """True sideways drift, heading error and forward distance - the evaluation's measures.
        The control loop never sees these; only the comparison scripts do."""
        fwd = np.array([-math.sin(self.start_yaw), math.cos(self.start_yaw)])
        right = np.array([math.cos(self.start_yaw), math.sin(self.start_yaw)])
        rel = self.d.qpos[:2] - self.start_xy
        h = self.body_yaw() - self.start_yaw
        return {"side_mm": 1000 * rel @ right, "fwd_mm": 1000 * rel @ fwd,
                "heading_deg": math.degrees(math.atan2(math.sin(h), math.cos(h))),
                "tilt_deg": math.degrees(math.acos(max(-1.0, min(1.0, self.d.xmat[self.body][8]))))}

    # ------------------------------------------------------------ the interface
    def connect(self):
        self._connected = True
        self.yaw_at_connect = self.body_yaw()          # like imu_reset_yaw_axis()
        self.t_connect = self.d.time
        self.wall_start = time.monotonic()
        self._take_sensor_message()

    @property
    def connected(self) -> bool:
        return self._connected

    def now(self) -> float:
        return self.d.time

    def read(self) -> Reading:
        if not self._connected:
            raise ConnectionError("FakeRobot: not connected")
        return self.last

    def send(self, right_pct: int, left_pct: int):
        if not self._connected:
            raise ConnectionError("FakeRobot: not connected")
        self.wanted = np.array([self._pct_to_joint_speed("right", right_pct),
                                self._pct_to_joint_speed("left", left_pct)])

    def stop(self):
        # Like the real robot: a stop can only be sent over a working link, and it also
        # travels through the Bluetooth delay like any command.
        if not self._connected:
            raise ConnectionError("FakeRobot: not connected, stop cannot reach the hub")
        self.wanted = np.zeros(2)

    def close(self):
        if self._connected:
            self.stop()
        self._connected = False

    def wait_until(self, t: float):
        while self.d.time + 1e-9 < t:
            before = self.d.time
            self._physics_step()
            if self.d.time <= before:
                # MuJoCo resets its clock to 0 when the simulation blows up (NaN); without
                # this check the loop would wait for time t forever.
                raise RuntimeError(f"FakeRobot: the simulation became unstable at t={before:.3f} s")
            if self.realtime:
                lag = (self.d.time - self.t_connect) - (time.monotonic() - self.wall_start)
                if lag > 0.002:
                    time.sleep(lag)

    # ------------------------------------------------------------ test hooks
    def disconnect(self):
        """Simulate a lost Bluetooth link: the motors keep their last command (as a real
        hub might), and read()/send() fail."""
        self._connected = False

    def freeze_sensors(self):
        """Simulate a link that stays 'connected' but stops delivering sensor messages."""
        self._sensors_frozen = True

    def tip_over(self, duration_s: float = 0.5):
        """Roll the robot onto its side, to test the tip-over stop: a twist of 0.04 N m about
        the robot's own front-to-back axis (its weight resists with at most ~0.024 N m),
        released once the robot is past 100 deg or after duration_s."""
        self._tip_until = self.d.time + duration_s

    # ------------------------------------------------------------ internals
    def _pct_to_joint_speed(self, side: str, pct: int) -> float:
        """Percent -> simulator joint speed (rad/s). The upright direction is NEGATIVE."""
        rad_s = U.percent_to_rpm(pct) * 2 * math.pi / 60 * self.motor_scale[side]
        upright = (pct * C.UPRIGHT_PERCENT_SIGN[side]) > 0
        return -rad_s if upright else rad_s

    def _physics_step(self):
        # Bluetooth delay: same model as MJLab's actuator delay buffer
        self.history.append(self.wanted.copy())
        self.history = self.history[-(self.delay_range[1] + 1):]
        if self.rng.random() > self.hold_prob:
            self.lag = int(self.rng.integers(self.delay_range[0], self.delay_range[1] + 1))
        applied = self.history[-1 - min(self.lag, len(self.history) - 1)]
        self.d.ctrl[self.act["right"]], self.d.ctrl[self.act["left"]] = applied
        self.d.xfrc_applied[self.body] = 0.0
        if self.d.time < self._tip_until and self.truth()["tilt_deg"] < 100:
            front = self.d.xmat[self.body].reshape(3, 3)[:, 1]     # body +y in the world
            self.d.xfrc_applied[self.body, 3:] = 0.04 * front       # torque (world frame)
        mujoco.mj_step(self.m, self.d)
        if self.d.time + 1e-9 >= self.next_sensor_t:
            self._take_sensor_message()

    def _take_sensor_message(self):
        self.next_sensor_t = self.d.time + SENSOR_PERIOD_S
        if self._sensors_frozen:
            return
        rng, N, on = self.rng, U.META["noise"], self.noise
        Rb = self.d.xmat[self.body].reshape(3, 3)          # body -> world rotation
        # tilt: gravity direction in body axes (+ training's tilt noise), as pitch/roll
        g_body = Rb.T @ np.array([0.0, 0.0, -1.0])
        if on:
            g_body = g_body + N["tilt"] * rng.standard_normal(3)
        pitch, roll = U.pitch_roll_from_gravity(U.HUB_FROM_BODY @ g_body)
        # accelerometer: specific force = acceleration - gravity, in g (reads +1 g up at rest)
        a_world = self.d.qacc[:3] - self.m.opt.gravity
        accel = U.HUB_FROM_BODY @ (Rb.T @ a_world) / 9.81 * 1000
        # gyroscope: MuJoCo keeps the free joint's angular velocity in BODY axes
        w = self.d.qvel[3:6] + (N["gyro_rad_s"] * rng.standard_normal(3) if on else 0.0)
        gyro = C.GYRO_SIGN * np.degrees(U.HUB_FROM_BODY @ w)
        # yaw since connect, with slow drift and noise
        t = self.d.time - getattr(self, "t_connect", 0.0)
        h = self.body_yaw() - self.yaw_at_connect + self.yaw_drift * t
        if on:
            h += N["heading_rad"] * rng.standard_normal()
        h = math.atan2(math.sin(h), math.cos(h))
        unit = C.ANGLE_UNIT_DEG
        motors = {}
        for s in ("right", "left"):
            q = self.d.qpos[self.qadr[s]]
            noisy_q = q + self.leg_calib[s] + (N["leg_angle_rad"] * rng.standard_normal() if on else 0.0)
            enc = C.ENCODER_SIGN[s] * math.degrees(noisy_q)          # encoder direction
            enc_counted = C.ENCODER_SIGN[s] * math.degrees(q + self.leg_calib[s])
            # the hub's own speed report: actual leg speed as a percent (sign: + = upright)
            v = self.d.qvel[self.vadr[s]]
            pct_now = U.rpm_to_percent(abs(v) * 60 / (2 * math.pi))
            motors[s] = MotorReading(
                absolute_deg=int(round(enc + C.LEG_ZERO_DEG[s])) % 360,
                position_deg=int(round(enc_counted)),
                # one signed byte on the real hub: -127..127
                speed_pct=int(np.clip(round(pct_now), 0, 127)) * (1 if v < 0 else -1)
                          * C.UPRIGHT_PERCENT_SIGN[s])
        self.count += 1
        self.last = Reading(
            t=self.d.time, count=self.count,
            accel_mg=tuple(int(round(v)) for v in accel),
            gyro_dps=tuple(int(round(v)) for v in gyro),
            yaw=int(round(C.YAW_SIGN * math.degrees(h) / unit)),
            pitch=int(round(C.PITCH_SIGN * math.degrees(pitch) / unit)),
            roll=int(round(C.ROLL_SIGN * math.degrees(roll) / unit)),
            motors=motors)
