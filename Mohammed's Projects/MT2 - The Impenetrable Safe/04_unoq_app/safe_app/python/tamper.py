"""
tamper.py - the tamper alarm: someone knocking, shaking or prying the box.

The MPU-6050 on the box floor is read by the sketch 100 times a second. The
sketch turns each reading into two movement numbers and keeps the biggest
of each since Python last asked (see sketch.ino):
    shake  how far the acceleration jumped from its recent average, in mg
           (thousandths of gravity). Still: close to 0. A knock: a spike.
    turn   how fast the box rotates (beyond the sensor's own offset), deg/s.

THE ALARM RULE
  * Only while the board reports the latch LOCKED. When it's open, moving
    the box is normal.
  * Never because of the safe's own motor. The sketch ignores movement while
    the latch moves and for 1 s after (it reports those moments as "quiet").
  * If shake or turn passes its threshold, the alarm is on for ALARM_S
    seconds (each new jolt restarts the count). The LED matrix flashes a
    warning and the web page shows TAMPER ALERT.
  * It only warns. It doesn't change the lock's rules or lock anything out.

The thresholds come from calibration on the real box (see the numbers at
SHAKE_ALARM_MG and the README's build log): well above the still box, and
below the gentlest try at lifting the locked lid.
"""

# ---- Settings (from calibration; see the build log) ---------------------------
# Calibrated on the real box (2026-11-09):
#   still box:            shake <= 25 mg,  turn <= 2 deg/s   (sensor noise)
#   gentle knocks:        31-64 mg,        <= 11 deg/s       -> ignored on purpose (a tap isn't prying)
#   lifting the locked lid: 71-251 mg,     15-38 deg/s       -> must alarm
#   firm knocks / slide / shake: 47-2800 mg, 6-140 deg/s     -> alarm
#   hand resting on the lid: ~70 mg, ~15 deg/s               -> alarms too (can't be told apart
#                                                               from the gentlest lid try)
# So: 3x the still noise in shake, 6x in turn, and the turn threshold below
# the gentlest lid try (15 deg/s), which barely moved the shake number (71 mg).
SHAKE_ALARM_MG = 80.0
TURN_ALARM_DPS = 12.0
ALARM_S = 5.0             # how long the alarm stays on after the last jolt


class TamperWatch:
    def __init__(self):
        self.sensor_ok = None     # True / False once the sketch has answered; None before
        self.alarm_until = 0.0
        self.alarms = 0           # how many separate alarms since start (for the log)

    def update(self, reading, latch_state, now):
        """reading: the sketch's motion() answer, or None if the Bridge call failed.

        Returns (shake, turn, quiet) for logging, or None.
        """
        if not reading:
            self.sensor_ok = None
            return None
        found, _who, shake, turn, _ax, _ay, _az, quiet = reading
        self.sensor_ok = bool(found)
        if not found:
            return None
        quiet = bool(quiet)
        jolt = shake >= SHAKE_ALARM_MG or turn >= TURN_ALARM_DPS
        if latch_state == "locked" and not quiet and jolt:
            if not self.active(now):              # a new alarm (not a jolt during one already on)
                print(f"TAMPER ALERT: shake {shake:.0f} mg, turn {turn:.0f} deg/s")
                self.alarms += 1
            self.alarm_until = now + ALARM_S
        return shake, turn, quiet

    def active(self, now):
        return now < self.alarm_until

    def seconds_left(self, now):
        return max(0.0, self.alarm_until - now)
