"""
RealRobot: the LEGO Education Double Motor over Bluetooth, behind the robot interface.

Uses the same library and calls as MT1 (legoeducation 1.2.0, in the main .venv):
  dm = le.DoubleMotor(); dm.connect(device_notification_delay=20)   ask for a sensor
                                                                   message every 20 ms
  dm.imu_device   -> accelerometerX/Y/Z (milli-g), gyroscopeX/Y/Z (deg/s), yaw/pitch/roll
  dm.motor[i]     -> absolutePosition, position, speed  for i = le.MOTOR_LEFT / le.MOTOR_RIGHT
  dm.movement_move_tank(left %, right %)    both speeds in ONE Bluetooth message
  dm.movement_stop(), dm.imu_reset_yaw_axis(), dm.disconnect()

How it works:
  - The library updates dm.imu_device / dm.motor in the background whenever a sensor
    message arrives. We also register a notification callback that only notes the arrival
    time and counts messages: that is how the control loop can tell FRESH data from stale.
  - read_lego()/send_lego() use the library's own left/right (le.MOTOR_LEFT = 0,
    le.MOTOR_RIGHT = 1); read()/send() (from RobotInterface) map them to the ROBOT's legs
    with config.ROBOT_RIGHT_IS_LEGO, so the control loop speaks in robot legs.
  - Commands are sent without waiting for the hub's reply (blocking=False), so a slow
    reply cannot stall the 20 Hz loop; the stop command DOES wait (blocking=True) so we
    know it arrived.
Nothing here has run on the real hub yet; tests/test_real_robot_dryrun.py checks it against
a stand-in built from the library's own message classes.
"""

import time

import legoeducation as le

import config as C
from robot_interface import MotorReading, Reading, RobotInterface

FIRST_MESSAGE_TIMEOUT_S = 3.0


class RealRobot(RobotInterface):
    def __init__(self, device_factory=le.DoubleMotor):
        self.dm = device_factory()
        self.msg_time = None
        self.msg_count = 0
        self.index = {"left": le.MOTOR_LEFT, "right": le.MOTOR_RIGHT}    # LEGO side -> list index

    def _on_message(self, _data):
        """Called by the library's Bluetooth thread for every sensor message."""
        self.msg_time = time.monotonic()
        self.msg_count += 1

    # ------------------------------------------------------------ interface
    def connect(self):
        print("Searching for the Double Motor... (turn it on; it should blink)")
        self.dm.connect(device_notification_delay=C.NOTIFICATION_MS)
        if not self.dm.connected:
            raise ConnectionError("Could not connect. Is it charged, on, and not connected elsewhere?")
        self.dm.set_notification_callback(self._on_message)
        self.dm.movement_stop()                 # start from a known, stopped state
        self.dm.imu_reset_yaw_axis()            # heading 0 = the direction it faces now
        start = time.monotonic()
        n0 = self.msg_count
        while self.msg_count <= n0 + 1:         # wait for fresh data after the yaw reset
            if time.monotonic() - start > FIRST_MESSAGE_TIMEOUT_S:
                raise ConnectionError("Connected, but no sensor messages arrive")
            time.sleep(0.01)
        print("Connected.")

    @property
    def connected(self) -> bool:
        return bool(self.dm.connected)

    def now(self) -> float:
        return time.monotonic()

    def wait_until(self, t: float):
        dt = t - time.monotonic()
        if dt > 0:
            time.sleep(dt)

    def read_lego(self) -> Reading:
        if not self.dm.connected:
            raise ConnectionError("Double Motor disconnected")
        imu = self.dm.imu_device
        motors = {}
        for side in ("right", "left"):                 # LEGO sides
            mn = self.dm.motor[self.index[side]]
            motors[side] = MotorReading(absolute_deg=int(mn.absolutePosition),
                                        position_deg=int(mn.position), speed_pct=int(mn.speed))
        return Reading(t=self.msg_time, count=self.msg_count,
                       accel_mg=(imu.accelerometerX, imu.accelerometerY, imu.accelerometerZ),
                       gyro_dps=(imu.gyroscopeX, imu.gyroscopeY, imu.gyroscopeZ),
                       yaw=imu.yaw, pitch=imu.pitch, roll=imu.roll, motors=motors)

    def send_lego(self, lego_left_pct: int, lego_right_pct: int):
        if not self.dm.connected:
            raise ConnectionError("Double Motor disconnected")
        clamp = lambda x: int(max(-100, min(100, x)))
        self.dm.movement_move_tank(clamp(lego_left_pct), clamp(lego_right_pct), blocking=False)

    def stop(self):
        if not self.dm.connected:
            raise ConnectionError("Double Motor disconnected; stop cannot be sent")
        self.dm.movement_stop(blocking=True)

    def close(self):
        try:
            if self.dm.connected:
                self.dm.movement_stop(blocking=True)
        finally:
            self.dm.disconnect()
            print("Disconnected.")
