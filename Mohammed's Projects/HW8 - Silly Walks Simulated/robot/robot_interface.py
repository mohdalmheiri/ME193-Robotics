"""
The one small "robot interface" the control loop talks to.

Two robots implement it:
  RealRobot (real_robot.py)  - the LEGO Double Motor over Bluetooth
  FakeRobot (fake_robot.py)  - the training simulator, pretending to be that hub
The control loop (run_policy.py) only ever calls the four methods below, so it cannot tell
which one it is driving.

Everything crossing this interface is in the REAL hub's units (what the LEGO library
reports), never in simulator units. Turning these into the policy's inputs happens in
exactly one place: units.py.
"""

from dataclasses import dataclass, field, replace

import config as C


@dataclass
class MotorReading:
    """One motor's latest report (fields named like the LEGO MotorNotification)."""
    absolute_deg: int          # absolutePosition: 0..359 degrees, survives restarts
    position_deg: int          # position: counted degrees since connecting (keeps counting
                               # past 360; used for leg speed)
    speed_pct: int             # speed: the hub's own speed report, percent (logged only;
                               # its exact meaning is checked by calibration/measure_rpm.py)


@dataclass
class Reading:
    """Latest sensor values, in the hub's units."""
    t: float                   # time this data arrived (s, the robot's own clock)
    count: int                 # how many sensor messages have arrived so far
    accel_mg: tuple            # accelerometer x, y, z in milli-g (reads ~+1000 "up" at rest)
    gyro_dps: tuple            # gyroscope x, y, z in deg/s
    yaw: int                   # hub angles, in config.ANGLE_UNIT_DEG units
    pitch: int
    roll: int
    motors: dict = field(default_factory=dict)   # {"right": MotorReading, "left": ...}
                                                  # keyed by LEGO side from read_lego(),
                                                  # by ROBOT leg from read()


def lego_side(robot_side: str) -> str:
    """Which LEGO motor ("left"/"right" in the library's naming) drives this robot leg,
    according to config.ROBOT_RIGHT_IS_LEGO (what the laptop believes)."""
    same = C.ROBOT_RIGHT_IS_LEGO == "right"
    return robot_side if same else {"right": "left", "left": "right"}[robot_side]


def to_robot_sides(lego_reading: Reading) -> Reading:
    """A reading whose motors are keyed by LEGO side -> keyed by robot leg (via config)."""
    return replace(lego_reading, motors={s: lego_reading.motors[lego_side(s)] for s in ("right", "left")})


class RobotInterface:
    """What every robot must offer. All speeds are percent, -100..100.

    Two levels:
      read_lego() / send_lego(left, right)   the LEGO library's own motor sides, no
                                             assumptions (used by the calibration scripts)
      read() / send(right, left)             ROBOT legs, mapped with config.py (used by the
                                             control loop); built on the two above
    """

    def read_lego(self) -> Reading:
        """Latest sensor values, motors keyed by LEGO side ("left"/"right")."""
        raise NotImplementedError

    def send_lego(self, lego_left_pct: int, lego_right_pct: int) -> None:
        """movement_move_tank(left, right) exactly as the library names the motors."""
        raise NotImplementedError

    def read(self) -> Reading:
        """Return the most recent sensor values (does not wait for new ones), per robot leg."""
        return to_robot_sides(self.read_lego())

    def send(self, right_pct: int, left_pct: int) -> None:
        """Set both leg speeds at once (one message on the real robot), per robot leg."""
        pct = {lego_side("right"): right_pct, lego_side("left"): left_pct}
        self.send_lego(pct["left"], pct["right"])

    def connect(self) -> None:
        """Open the connection, reset the heading to 0, motors stopped."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop both motors. Must be safe to call at any time, even twice."""
        raise NotImplementedError

    def close(self) -> None:
        """Stop and disconnect."""
        raise NotImplementedError

    @property
    def connected(self) -> bool:
        raise NotImplementedError

    def now(self) -> float:
        """The robot's clock (s). Real: wall clock. Fake: simulated time."""
        raise NotImplementedError

    def wait_until(self, t: float) -> None:
        """Wait until the robot's clock reaches t. Real: sleep. Fake: run the physics."""
        raise NotImplementedError
