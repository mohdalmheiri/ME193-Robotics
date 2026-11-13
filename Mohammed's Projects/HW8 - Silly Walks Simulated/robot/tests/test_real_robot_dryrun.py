"""
Dry run of RealRobot without the robot: catches typos and wrong calls before the session.

How it works:
  1. Checks that every LEGO library method RealRobot calls really exists on
     legoeducation.DoubleMotor, with the parameter names we pass (inspect.signature).
  2. Replaces the Bluetooth device with a stand-in ("StubDoubleMotor") that holds the
     library's OWN message classes (le.ImuDeviceNotification, le.MotorNotification) and
     calls the notification callback every 31 ms from a background thread, like the real
     library. It records every command it receives.
  3. Runs the real control loop (run_policy.run) on RealRobot + stand-in for 1 s, then
     checks: the loop ran ~20 decisions, the tank command got (LEGO left, LEGO right) in
     the right order for the configured side mapping, speeds were whole percents within
     -100..100, the final stop was sent and the device disconnected.
  4. Same with the stand-in "dropping" the connection, and with it going silent.

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_real_robot_dryrun.py
"""

import inspect
import sys
import threading
import time
from pathlib import Path

import legoeducation as le

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))
import config as C  # noqa: E402
from real_robot import RealRobot  # noqa: E402
from run_policy import run  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ({detail})" if detail else ""))


print("1. Library calls exist with the parameters we use")
USED = {"connect": ["device_notification_delay"], "set_notification_callback": ["callback"],
        "movement_stop": ["blocking"], "imu_reset_yaw_axis": [], "disconnect": [],
        "movement_move_tank": ["speed_left", "speed_right", "blocking"]}
for name, params in USED.items():
    fn = getattr(le.DoubleMotor, name, None)
    ok = fn is not None and all(p in inspect.signature(fn).parameters for p in params)
    check(f"DoubleMotor.{name}({', '.join(params)})", ok)
check("le.MOTOR_LEFT / le.MOTOR_RIGHT are the motor list indices 0 / 1",
      (le.MOTOR_LEFT, le.MOTOR_RIGHT) == (0, 1), f"{le.MOTOR_LEFT}, {le.MOTOR_RIGHT}")


class StubDoubleMotor:
    """Stand-in for le.DoubleMotor: same attributes, library message classes, no Bluetooth."""
    def __init__(self):
        self.connected = False
        self.silent = False
        self.calls = []
        self.imu_device = le.ImuDeviceNotification(0, 0, 0, 0, 0, 0, 0, 1000, 0, 0, 0)
        self.motor = [le.MotorNotification(1, 0, 0, 0, 0, 0, 0), le.MotorNotification(2, 0, 90, 0, 0, 0, 0)]
        self._cb = None

    def connect(self, device_notification_delay=100):
        self.connected = True
        self.calls.append(("connect", device_notification_delay))
        threading.Thread(target=self._stream, daemon=True).start()

    def _stream(self):
        while self.connected:
            time.sleep(0.031)
            if self._cb and not self.silent:
                for m in self.motor:
                    m.position += 3            # legs turning slowly
                self._cb(b"")

    def set_notification_callback(self, callback):
        self._cb = callback

    def movement_stop(self, blocking=True):
        self.calls.append(("stop",))

    def imu_reset_yaw_axis(self, value=0, blocking=True):
        self.calls.append(("reset_yaw",))

    def movement_move_tank(self, speed_left, speed_right, blocking=True):
        self.calls.append(("tank", speed_left, speed_right, blocking))

    def disconnect(self):
        self.connected = False
        self.calls.append(("disconnect",))


print("\n2. One second of the real control loop on RealRobot + stand-in")
for mapping in ("right", "left"):
    C.ROBOT_RIGHT_IS_LEGO = mapping
    stub = StubDoubleMotor()
    robot = RealRobot(device_factory=lambda: stub)
    s = run(robot, 1.0, None, quiet=True)
    tanks = [c for c in stub.calls if c[0] == "tank"]
    check(f"[ROBOT_RIGHT_IS_LEGO={mapping}] ran ~20 decisions, ended on the time limit",
          s["reason"] == "time limit reached" and 18 <= s["decisions"] <= 20, f"{s['decisions']}, {s['reason']}")
    check(f"[{mapping}] asked for a message every {C.NOTIFICATION_MS} ms and reset the heading",
          ("connect", C.NOTIFICATION_MS) in stub.calls and ("reset_yaw",) in stub.calls)
    check(f"[{mapping}] tank speeds are whole percents in -100..100, sent without waiting",
          all(isinstance(c[1], int) and isinstance(c[2], int) and -100 <= c[1] <= 100 and -100 <= c[2] <= 100
              and c[3] is False for c in tanks), f"first {tanks[0][1:3] if tanks else None}")
    check(f"[{mapping}] ends with stop then disconnect", stub.calls[-2:] == [("stop",), ("disconnect",)],
          f"{stub.calls[-2:]}")
    # side mapping: robot right leg = LEGO right (index 1) unless mapping says left. The
    # stand-in's LEGO right motor reads absolutePosition 90; check RealRobot reports it on
    # the configured robot side.
    r = RealRobot(device_factory=StubDoubleMotor)
    r.dm.connected = True
    reading = r.read()
    expect_side = "right" if mapping == "right" else "left"
    check(f"[{mapping}] LEGO right motor shows up as the robot's {expect_side} leg",
          reading.motors[expect_side].absolute_deg == 90)
C.ROBOT_RIGHT_IS_LEGO = "right"

print("\n3. Problems")
stub = StubDoubleMotor()
s = run(RealRobot(device_factory=lambda: stub), 5.0, None, quiet=True,
        on_decision=lambda k, r: setattr(stub, "connected", False) if k == 10 else None)
check("dropped connection -> 'connection lost' at once", s["reason"].startswith("connection lost")
      and s["decisions"] == 10, f"{s['reason']}, {s['decisions']} decisions")
stub = StubDoubleMotor()
s = run(RealRobot(device_factory=lambda: stub), 5.0, None, quiet=True,
        on_decision=lambda k, r: setattr(stub, "silent", True) if k == 10 else None)
check("silent link -> 'stale sensors' within 0.35 s, then stop sent",
      s["reason"].startswith("stale") and s["decisions"] <= 10 + 7 and ("stop",) in stub.calls,
      f"{s['reason']}, {s['decisions']} decisions")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
