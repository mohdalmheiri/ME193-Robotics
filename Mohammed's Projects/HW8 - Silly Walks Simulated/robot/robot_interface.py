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

from dataclasses import dataclass, field


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
                                                  # (already mapped to ROBOT sides)


class RobotInterface:
    """What every robot must offer. All speeds are percent, -100..100, per ROBOT side."""

    def connect(self) -> None:
        """Open the connection, reset the heading to 0, motors stopped."""
        raise NotImplementedError

    def read(self) -> Reading:
        """Return the most recent sensor values (does not wait for new ones)."""
        raise NotImplementedError

    def send(self, right_pct: int, left_pct: int) -> None:
        """Set both leg speeds at once (one message on the real robot)."""
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
