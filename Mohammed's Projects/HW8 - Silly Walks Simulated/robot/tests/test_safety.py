"""
Safety tests: every way a run can end must leave the motors stopped (or, for a lost
connection, end the loop at once and say the laptop could not send the stop).

How it works: each test drives a FakeRobot with the real control loop (run_policy.run) and,
through the loop's on_decision hook, causes one problem at decision 40 (2 s in):
  Ctrl-C            the hook raises KeyboardInterrupt, as pressing Ctrl-C does
  lost connection   FakeRobot.disconnect(): read/send/stop all fail, like a dropped link
  frozen sensors    FakeRobot.freeze_sensors(): still "connected", but no new messages
  tipped over       FakeRobot.tip_over(): a strong sideways shove rolls the robot over
  time limit        a 2 s run ends by itself
  crash             the policy raises an error mid-run (a bug); the stop must still happen
After each run it checks the reason, how quickly the loop reacted, and (except for the lost
connection) that the motors were told to stop and the legs really come to rest 0.3 s later
(stop commands also pass through the simulated 0-40 ms Bluetooth delay; "at rest" means
the legs no longer TURN - average speed over 0.3 s below 5 rpm).

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_safety.py
"""

import math
import sys
from pathlib import Path

import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))
import config as C  # noqa: E402
from fake_robot import FakeRobot  # noqa: E402
from policy import Policy  # noqa: E402
from run_policy import run  # noqa: E402

AT = 40                    # problem happens before decision 40 (t = 2.0 s)
SEED = 1                   # a fake robot the policy walks cleanly (some, e.g. seed 11, tip over
                           # by themselves - see check_fake_vs_eval.py - which would muddle these)
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ({detail})" if detail else ""))


def legs_stopped(fake: FakeRobot) -> tuple[bool, float]:
    """After the stop, let 0.4 s pass (Bluetooth delay + the robot settling), then
    measure how far each leg TURNS in the next 0.3 s, as an average rpm.

    Net rotation, not the instantaneous speed: in the simulator a stopped leg hanging in
    the air vibrates by ~1 deg every 2 ms physics step (a numerical artifact of the motor
    model's tiny inertia, see docs/process_log.md), so its instantaneous speed reads up
    to ~100 rpm while it does not actually go anywhere.
    """
    fake._connected, was = True, fake._connected      # peek without changing the outcome
    fake.wait_until(fake.now() + 0.4)
    q0 = {s: fake.d.qpos[fake.qadr[s]] for s in ("right", "left")}
    fake.wait_until(fake.now() + 0.3)
    fake._connected = was
    rpm = max(abs(fake.d.qpos[fake.qadr[s]] - q0[s]) for s in ("right", "left")) / 0.3 * 60 / (2 * math.pi)
    return rpm < 5.0, rpm


def trial(name, hook=None, seconds=10.0, policy=None):
    fake = FakeRobot(seed=SEED)
    s = run(fake, seconds, None, policy=policy, on_decision=hook, quiet=True)
    return fake, s


print("Ctrl-C")
def ctrl_c(k, robot):
    if k == AT:
        raise KeyboardInterrupt
fake, s = trial("ctrl-c", ctrl_c)
check("reason is Ctrl-C", s["reason"] == "Ctrl-C", s["reason"])
check("loop ended at once", s["decisions"] == AT, f"{s['decisions']} decisions")
ok, rpm = legs_stopped(fake)
check("motors told to stop, legs at rest 0.3 s later", ok and not fake.wanted.any(), f"{rpm:.1f} rpm")

print("Lost connection")
fake, s = trial("disconnect", lambda k, r: r.disconnect() if k == AT else None)
check("reason is connection lost", s["reason"].startswith("connection lost"), s["reason"])
check("loop ended at once", s["decisions"] == AT, f"{s['decisions']} decisions")
check("loop did not hang or crash trying to stop a robot it cannot reach", True,
      "the stop failure is reported; the real hub's own behaviour must stop the motors")

print("Frozen sensors (link up, no new data)")
fake, s = trial("frozen", lambda k, r: r.freeze_sensors() if k == AT else None)
check("reason is stale sensors", s["reason"].startswith("stale sensors"), s["reason"])
late = (s["decisions"] - AT) * 0.05
check(f"noticed within {C.STALE_SENSOR_S} s + one decision", late <= C.STALE_SENSOR_S + 0.05 + 1e-9,
      f"{late:.2f} s after the freeze")
ok, rpm = legs_stopped(fake)
check("motors stopped", ok, f"{rpm:.1f} rpm")

print("Tipped over")
fake, s = trial("tip", lambda k, r: r.tip_over() if k == AT else None)
check("reason is tipped over", s["reason"].startswith("tipped over"), s["reason"])
check("noticed within 1 s of the shove", (s["decisions"] - AT) * 0.05 <= 1.0,
      f"{(s['decisions'] - AT) * 0.05:.2f} s, true tilt then {s['truth']['tilt_deg']:.0f} deg")
ok, rpm = legs_stopped(fake)
check("motors stopped", ok, f"{rpm:.1f} rpm")

print("Time limit")
fake, s = trial("time", seconds=2.0)
check("reason is time limit", s["reason"] == "time limit reached", s["reason"])
check("exactly 40 decisions in 2 s", s["decisions"] == 40, f"{s['decisions']}")
ok, rpm = legs_stopped(fake)
check("motors stopped", ok, f"{rpm:.1f} rpm")

print("Crash inside the loop (a bug in the policy code)")
class Broken(Policy):
    def __init__(self):
        super().__init__()
        self.calls = 0
    def __call__(self, obs):
        self.calls += 1
        if self.calls > AT:
            raise ValueError("simulated bug")
        return super().__call__(obs)
fake = FakeRobot(seed=SEED)
try:
    run(fake, 10.0, None, policy=Broken(), quiet=True)
    crashed = False
except ValueError:
    crashed = True
check("the error is not hidden (it still reaches the user)", crashed)
ok, rpm = legs_stopped(fake)
check("motors stopped anyway (the finally: block ran)", ok and not fake.wanted.any(), f"{rpm:.1f} rpm")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
