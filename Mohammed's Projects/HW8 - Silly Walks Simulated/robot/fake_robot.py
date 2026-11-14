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
  The hub's wiring and sensor conventions (which LEGO motor drives which leg, motor
            and encoder directions, leg zero, motion-sensor axes/units/signs, rpm per percent)
            are a hidden "true hub" (FakeRobot(hub={...}); default = config.py). The laptop side
            (read()/send(), units.py) uses config.py, i.e. what it BELIEVES - exactly like the
            real robot. The calibration tests give the fake hub a different truth and check
            that the calibration scripts find it.
  v2 extras  With a v2 policy (policy_meta.json has them) each robot also draws its motor
            inertia (log-uniform), gearbox friction and contact stiffness from v2's ranges.
  Robustness options (not used by the normal checks):
            body_mass_kg=0.080   set the body's mass (inertia scaled with it)
            motor="regulated"    the SPEC MOTOR (config.MOTOR_SPEC: ~334 rpm no load, ~0.16 N m
                                 stall), with the hub holding the commanded speed: training's
                                 speed controller (torque = 0.05 x speed error), but limited by
                                 what a DC motor can give at its current speed,
                                 stall x (1 - speed / no-load speed) (minus that when braking)
            motor="pwm"          the SPEC MOTOR with NO speed control: the percent sets the
                                 motor voltage, torque = stall x (percent/100 - speed / no-load
                                 speed), so the speed sags under load
            Each side gets its own stall torque and no-load speed from the spec ranges.
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
LEGS = ("right", "left")
HUB_KEYS = ("ROBOT_RIGHT_IS_LEGO", "UPRIGHT_PERCENT_SIGN", "ENCODER_SIGN", "LEG_ZERO_DEG",
            "RPM_AT_PERCENT", "BODY_FROM_HUB", "ANGLE_UNIT_DEG", "PITCH_SIGN", "ROLL_SIGN",
            "YAW_SIGN", "GYRO_SIGN", "PITCH_ROLL_SWAPPED")


class FakeRobot(RobotInterface):
    def __init__(self, seed: int = 0, realtime: bool = False, randomize: bool = True,
                 noise: bool = True, legs_in_step: bool = False, start_q=None,
                 start_yaw: float | None = None, hub: dict | None = None,
                 armature: float | None = None, body_mass_kg: float | None = None,
                 motor: str | None = None):
        # the fake hub's TRUE wiring/conventions (default: exactly what config.py assumes)
        self.hub = {k: getattr(C, k) for k in HUB_KEYS}
        self.hub.update(hub or {})
        self.hub_from_body = U.axis_map(self.hub["BODY_FROM_HUB"]).T
        self._pct_tbl = np.array([p for p, _ in self.hub["RPM_AT_PERCENT"]], dtype=float)
        self._rpm_tbl = np.array([r for _, r in self.hub["RPM_AT_PERCENT"]], dtype=float)
        same = self.hub["ROBOT_RIGHT_IS_LEGO"] == "right"
        self.leg_of_lego = {"right": "right" if same else "left", "left": "left" if same else "right"}
        self.lego_of_leg = {leg: lego for lego, leg in self.leg_of_lego.items()}
        self.rng = np.random.default_rng(seed)
        self.realtime, self.randomize, self.noise = realtime, randomize, noise
        self.m = mujoco.MjModel.from_xml_path(str(U.MODEL_DIR / "scene.xml"))
        self.d = mujoco.MjData(self.m)
        self.dt = self.m.opt.timestep
        self.g_world = self.m.opt.gravity.copy()   # what the fake accelerometer feels, always
        self.body = self.m.body("robot/body").id
        self.qadr = {s: self.m.jnt_qposadr[self.m.joint(j).id] for s, j in JOINT.items()}
        self.vadr = {s: self.m.jnt_dofadr[self.m.joint(j).id] for s, j in JOINT.items()}
        self.act = {s: self.m.actuator(j).id for s, j in JOINT.items()}
        # motor inertia override (applied after the randomization). v1's model has 1e-5, which
        # makes the simulated speed controller chatter; an unloaded leg then averages ~81 rpm
        # WHATEVER the command (docs/process_log.md). v2 trains with 2e-4 nominal.
        self.armature_override = armature
        self.body_mass_kg = body_mass_kg
        assert motor in (None, "regulated", "pwm"), motor
        self.motor = motor
        self.kv_train = float(self.m.actuator_gainprm[self.act["right"], 0])   # 0.05 N m / (rad/s)
        self._connected = False
        self._sensors_frozen = False
        self._tip_until = -1.0
        self._held = False                    # hold_pose(): physics paused, body held by "hand"
        self._turn = None                     # hold_turn(): (t0, degrees, seconds)
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
            if "armature_kg_m2" in R:         # v2's extra randomizations
                lo, hi = (math.log(x) for x in R["armature_kg_m2"])
                for s in LEGS:
                    m.dof_armature[self.vadr[s]] = self.info[f"armature_{s}"] = math.exp(rng.uniform(lo, hi))
                    m.dof_frictionloss[self.vadr[s]] *= rng.uniform(*R["joint_friction_scale"])
                tc = self.info["contact_timeconst"] = rng.uniform(*R["contact_timeconst_s"])
                for g in ("robot/body_box", "robot/hub_right", "robot/hub_left",
                          "robot/leg_right_box", "robot/leg_left_box"):
                    m.geom_solref[m.geom(g).id, 0] = tc
        if self.armature_override is not None:
            for s in LEGS:
                m.dof_armature[self.vadr[s]] = self.armature_override
        if self.body_mass_kg is not None:
            k = self.body_mass_kg / m.body_mass[self.body]
            m.body_mass[self.body] *= k
            m.body_inertia[self.body] *= k
        self.spec = {}
        if self.motor:
            # spec motor: per side, a stall torque and no-load speed from the published ranges
            S = C.MOTOR_SPEC
            pick = (lambda r: rng.uniform(*r)) if self.randomize else (lambda r: sum(r) / 2)
            for s in LEGS:
                self.spec[s] = {"stall": pick(S["stall_torque_Nm"]),
                                "w0": pick(S["no_load_rpm"]) * 2 * math.pi / 60}
                a = self.act[s]
                kv = self.kv_train if self.motor == "regulated" else self.spec[s]["stall"] / self.spec[s]["w0"]
                m.actuator_gainprm[a, 0], m.actuator_biasprm[a, 2] = kv, -kv
            self.info["spec_motor"] = self.spec
        mujoco.mj_setConst(m, self.d)         # recompute quantities that depend on mass
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

    @property
    def turn_unwrapped_deg(self) -> float:
        """True heading change since the start, counting whole turns (+ = left)."""
        return math.degrees(getattr(self, "_turn_rad", 0.0))

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

    def read_lego(self) -> Reading:
        if not self._connected:
            raise ConnectionError("FakeRobot: not connected")
        return self.last                      # motors keyed by LEGO side

    def send_lego(self, lego_left_pct: int, lego_right_pct: int):
        """The fake hub's movement_move_tank: each LEGO motor drives the leg the TRUE wiring
        connects it to. (read()/send() per robot leg come from RobotInterface, via config.)"""
        if not self._connected:
            raise ConnectionError("FakeRobot: not connected")
        for lego, pct in (("left", lego_left_pct), ("right", lego_right_pct)):
            leg = self.leg_of_lego[lego]
            self.wanted[LEGS.index(leg)] = self._pct_to_joint_speed(leg, int(pct))

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

    # ------------------------------------------------------------ "hands" for calibration tests
    def on_stand(self):
        """Clamp the robot on a stand, legs spinning freely in the air: the body is lifted
        10 cm and put back in that exact pose, motionless, before every physics step (like
        a clamp). Normal physics otherwise, gravity included."""
        self.d.qpos[2] = 0.10
        self.d.qvel[:6] = 0.0
        mujoco.mj_forward(self.m, self.d)
        self._stand_pose = self.d.qpos[:7].copy()

    def pose_legs(self, q_right: float, q_left: float):
        """Someone turns the legs by hand to these simulator angles (rad) and lets go."""
        self.d.qpos[self.qadr["right"]], self.d.qpos[self.qadr["left"]] = q_right, q_left
        self.d.qvel[self.vadr["right"]] = self.d.qvel[self.vadr["left"]] = 0.0
        mujoco.mj_forward(self.m, self.d)
        self._take_sensor_message()

    def hold_pose(self, pitch_deg: float = 0.0, roll_deg: float = 0.0, yaw_deg: float = 0.0,
                  spin_dps: float = 0.0, message: bool = True):
        """Someone holds the body still in this orientation (pitch + = front UP, roll + = right
        side DOWN, yaw + = turned LEFT from the start), optionally turning it about the vertical
        at spin_dps (deg/s, + = to the LEFT). Physics is paused: the next sensor message is
        taken directly from this pose (the accelerometer then reads exactly -gravity)."""
        yaw = self.start_yaw + math.radians(yaw_deg)
        p, r = math.radians(pitch_deg), math.radians(roll_deg)
        cz, sz = math.cos(yaw / 2), math.sin(yaw / 2)
        cx, sx = math.cos(p / 2), math.sin(p / 2)
        cy, sy = math.cos(r / 2), math.sin(r / 2)
        qz, qx, qy = np.array([cz, 0, 0, sz]), np.array([cx, sx, 0, 0]), np.array([cy, 0, sy, 0])
        q = np.zeros(4)
        tmp = np.zeros(4)
        mujoco.mju_mulQuat(tmp, qz, qx)        # same order as units.gravity_from_pitch_roll:
        mujoco.mju_mulQuat(q, tmp, qy)         # yaw about z, then pitch about x, then roll about y
        self.d.qpos[3:7] = q
        self.d.qvel[:] = 0.0
        self.d.qacc[:] = 0.0
        Rb = np.zeros(9)
        mujoco.mju_quat2Mat(Rb, q)
        # turning about the WORLD vertical, expressed in body axes (MuJoCo's convention)
        self.d.qvel[3:6] = Rb.reshape(3, 3).T @ np.array([0.0, 0.0, math.radians(spin_dps)])
        mujoco.mj_kinematics(self.m, self.d)
        self._held = True
        self._held_pose = (pitch_deg, roll_deg, yaw_deg)
        if message:                           # a fresh sensor message from the new pose
            self._take_sensor_message()

    def hold_turn(self, degrees: float, seconds: float):
        """While held level, turn the robot by `degrees` (+ = LEFT) at a steady rate over
        `seconds`, starting now (the sensor messages see it turning)."""
        if not self._held:
            self.hold_pose()
        self._turn = (self.d.time, degrees, seconds, self._held_pose[2])

    def release(self):
        """Let go: physics runs again."""
        self._held = False
        self._turn = None

    # ------------------------------------------------------------ internals
    def _pct_to_joint_speed(self, leg: str, pct: int) -> float:
        """Percent -> simulator joint speed (rad/s), with the TRUE hub's rpm table and motor
        direction. The upright walking direction is a NEGATIVE joint speed."""
        rpm = float(np.interp(min(abs(pct), 100), self._pct_tbl, self._rpm_tbl))
        rad_s = rpm * 2 * math.pi / 60 * self.motor_scale[leg]
        upright = (pct * self.hub["UPRIGHT_PERCENT_SIGN"][leg]) > 0
        return -rad_s if upright else rad_s

    def _rpm_to_pct(self, rpm: float) -> float:
        """The TRUE hub's percent for a leg speed (for its speed report), linear above 100 %."""
        if rpm <= self._rpm_tbl[-1]:
            return float(np.interp(rpm, self._rpm_tbl, self._pct_tbl))
        return 100.0 * rpm / self._rpm_tbl[-1]

    def _physics_step(self):
        if self._held:                        # body held by hand: time passes, nothing moves
            self.d.time += self.dt
            if self._turn is not None:
                t0, deg, secs, yaw0 = self._turn
                frac = min(1.0, (self.d.time - t0) / secs)
                spin = deg / secs if frac < 1.0 else 0.0
                pitch, roll, _ = self._held_pose
                t_keep = self.d.time
                self.hold_pose(pitch, roll, yaw0 + deg * frac, spin_dps=spin, message=False)
                self.d.time = t_keep
                self._turn = (t0, deg, secs, yaw0) if frac < 1.0 else None
            if self.d.time + 1e-9 >= self.next_sensor_t:
                self._take_sensor_message()
            return
        # Bluetooth delay: same model as MJLab's actuator delay buffer
        self.history.append(self.wanted.copy())
        self.history = self.history[-(self.delay_range[1] + 1):]
        if self.rng.random() > self.hold_prob:
            self.lag = int(self.rng.integers(self.delay_range[0], self.delay_range[1] + 1))
        applied = self.history[-1 - min(self.lag, len(self.history) - 1)]
        if not self.motor:
            self.d.ctrl[self.act["right"]], self.d.ctrl[self.act["left"]] = applied
        else:
            # spec motor, still as MuJoCo's velocity actuator (torque = kv x (ctrl - speed),
            # computed implicitly, so it stays stable with light legs), with limits redone each step
            w_full = self._rpm_tbl[-1] * 2 * math.pi / 60      # leg speed at 100 % in the hub table
            for i, s in enumerate(LEGS):
                a, sp = self.act[s], self.spec[s]
                w = self.d.qvel[self.vadr[s]]
                if self.motor == "regulated":
                    # training's controller, but a DC motor at speed w can give at most
                    # stall x (1 - w/w0) forwards and stall x (1 + w/w0) braking
                    self.d.ctrl[a] = applied[i]
                    self.m.actuator_forcerange[a] = (sp["stall"] * (-1 - w / sp["w0"]),
                                                     sp["stall"] * (1 - w / sp["w0"]))
                else:
                    # pwm: voltage fraction u = percent / 100 -> torque = stall x (u - w/w0)
                    #     = (stall/w0) x (u w0 - w): a velocity actuator with kv = stall/w0
                    u = max(-1.0, min(1.0, applied[i] / w_full))
                    self.d.ctrl[a] = u * sp["w0"]
                    self.m.actuator_forcerange[a] = (-2 * sp["stall"], 2 * sp["stall"])
        if getattr(self, "_stand_pose", None) is not None:       # clamped on a stand
            self.d.qpos[:7] = self._stand_pose
            self.d.qvel[:6] = 0.0
        self.d.xfrc_applied[self.body] = 0.0
        if self.d.time < self._tip_until and self.truth()["tilt_deg"] < 100:
            front = self.d.xmat[self.body].reshape(3, 3)[:, 1]     # body +y in the world
            self.d.xfrc_applied[self.body, 3:] = 0.04 * front       # torque (world frame)
        mujoco.mj_step(self.m, self.d)
        # true heading change since the start, counting whole turns (for the drift test)
        yaw = self.body_yaw()
        prev = getattr(self, "_yaw_prev", self.start_yaw)
        self._turn_rad = getattr(self, "_turn_rad", 0.0) + math.atan2(math.sin(yaw - prev), math.cos(yaw - prev))
        self._yaw_prev = yaw
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
        pitch, roll = U.pitch_roll_from_gravity(self.hub_from_body @ g_body)
        # accelerometer: specific force = acceleration - gravity, in g (reads +1 g up at rest)
        a_world = self.d.qacc[:3] - self.g_world
        accel = self.hub_from_body @ (Rb.T @ a_world) / 9.81 * 1000
        # gyroscope: MuJoCo keeps the free joint's angular velocity in BODY axes
        w = self.d.qvel[3:6] + (N["gyro_rad_s"] * rng.standard_normal(3) if on else 0.0)
        gyro = self.hub["GYRO_SIGN"] * np.degrees(self.hub_from_body @ w)
        # yaw since connect, with slow drift and noise
        t = self.d.time - getattr(self, "t_connect", 0.0)
        h = self.body_yaw() - self.yaw_at_connect + self.yaw_drift * t
        if on:
            h += N["heading_rad"] * rng.standard_normal()
        h = math.atan2(math.sin(h), math.cos(h))
        unit, hub = self.hub["ANGLE_UNIT_DEG"], self.hub
        motors = {}
        for s in ("right", "left"):
            q = self.d.qpos[self.qadr[s]]
            noisy_q = q + self.leg_calib[s] + (N["leg_angle_rad"] * rng.standard_normal() if on else 0.0)
            enc = hub["ENCODER_SIGN"][s] * math.degrees(noisy_q)          # encoder direction
            enc_counted = hub["ENCODER_SIGN"][s] * math.degrees(q + self.leg_calib[s])
            # the hub's own speed report: actual leg speed as a percent (sign: + = upright)
            v = self.d.qvel[self.vadr[s]]
            pct_now = self._rpm_to_pct(abs(v) * 60 / (2 * math.pi))
            motors[self.lego_of_leg[s]] = MotorReading(          # keyed by LEGO side
                absolute_deg=int(round(enc + hub["LEG_ZERO_DEG"][s])) % 360,
                position_deg=int(round(enc_counted)),
                # one signed byte on the real hub: -127..127
                speed_pct=int(np.clip(round(pct_now), 0, 127)) * (1 if v < 0 else -1)
                          * hub["UPRIGHT_PERCENT_SIGN"][s])
        self.count += 1
        # same meaning as units.py: PITCH_SIGN / ROLL_SIGN belong to the pitch / roll VALUES;
        # PITCH_ROLL_SWAPPED then says the hub puts them in each other's fields
        pitch_field = int(round(hub["PITCH_SIGN"] * math.degrees(pitch) / unit))
        roll_field = int(round(hub["ROLL_SIGN"] * math.degrees(roll) / unit))
        if hub.get("PITCH_ROLL_SWAPPED"):
            pitch_field, roll_field = roll_field, pitch_field
        self.last = Reading(
            t=self.d.time, count=self.count,
            accel_mg=tuple(int(round(v)) for v in accel),
            gyro_dps=tuple(int(round(v)) for v in gyro),
            yaw=int(round(hub["YAW_SIGN"] * math.degrees(h) / unit)),
            pitch=pitch_field, roll=roll_field, motors=motors)
