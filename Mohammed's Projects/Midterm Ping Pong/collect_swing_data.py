# Step 6a: record labeled IMU data for the swing classifier.
# Run:  python collect_swing_data.py                 (30 swings + 60 s moving + 10 s still)
#       python collect_swing_data.py --swings 10 --idle 20 --still 5   (a shorter top-up)
# Every run APPENDS to swing_data.csv, so you can add more data later.
#
# Rows: session, t, ax, ay, az, gx, gy, gz, label, event
#   label "swing"     = the 1.5 s after a beep
#         "pause"     = between beeps (bringing the paddle back) - not used for training
#         "not_swing" = the moving-around and still rounds
#   event = which beep / which 2 s chunk the row belongs to (training splits by this)
import argparse
import csv
import os
import random
import threading
import time

import legoeducation as le

SWING_TIME = 1.5             # seconds after each beep that count as the swing
PAUSE = (1.5, 2.5)           # random pause between beeps (so you can't anticipate it)
IDLE_CHUNK = 2.0             # not-a-swing data is grouped into events of this many seconds
POLL = 0.005                 # check for a new IMU reading this often (readings come every 20 ms)
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swing_data.csv")
COLUMNS = ["session", "t", "ax", "ay", "az", "gx", "gy", "gz", "label", "event"]


class Recorder:
    """Background thread: saves every new IMU reading with the current label/event."""

    def __init__(self, dm, session):
        self.dm = dm
        self.session = session
        self.label, self.event = "pause", "start"
        self.rows = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def set(self, label, event):
        self.label, self.event = label, event

    def _loop(self):
        last = None
        while not self._stop.is_set():
            imu = self.dm.imu_device
            if imu is not last:   # the library swaps in a new object for each reading
                last = imu
                vals = [imu.accelerometerX, imu.accelerometerY, imu.accelerometerZ,
                        imu.gyroscopeX, imu.gyroscopeY, imu.gyroscopeZ]
                if all(v == v for v in vals):   # skip the NaN placeholder before the first reading
                    self.rows.append([self.session, f"{time.time():.4f}", *vals, self.label, self.event])
            time.sleep(POLL)

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1)


def countdown(seconds=3):
    for i in range(seconds, 0, -1):
        print(f"  {i}...")
        time.sleep(1)


def swing_round(dm, rec, n):
    print("\n" + "=" * 60)
    print(f"ROUND 1: {n} SWINGS")
    print("After each BEEP, swing like you do in the game (a quick push or")
    print("swing toward the screen) within 1.5 s. Then bring the paddle back")
    print("and wait for the next beep.")
    print("=" * 60)
    input("Press Enter when ready... ")
    countdown()
    for k in range(1, n + 1):
        rec.set("pause", f"{rec.session}-pause-{k}")
        time.sleep(random.uniform(*PAUSE))
        dm.beep()
        rec.set("swing", f"{rec.session}-swing-{k}")
        print(f"  SWING! ({k}/{n})")
        time.sleep(SWING_TIME)
    rec.set("pause", f"{rec.session}-pause-end")


def idle_round(rec, moving_s, still_s):
    print("\n" + "=" * 60)
    print(f"ROUND 2: {moving_s} s OF NOT-A-SWING")
    print("Move the paddle around normally WITHOUT swinging: get into position,")
    print("adjust, bring it back like after a swing, gentle moves.")
    print(f"After that, {still_s} s holding it still.")
    print("=" * 60)
    input("Press Enter when ready... ")
    countdown()
    start = time.time()
    total = moving_s + still_s
    told_still = False
    while (elapsed := time.time() - start) < total:
        rec.set("not_swing", f"{rec.session}-idle-{int(elapsed // IDLE_CHUNK)}")
        if elapsed >= moving_s and not told_still:
            told_still = True
            print("  Now HOLD STILL...")
        left = int(total - elapsed)
        if left % 10 == 0 and left > 0:
            print(f"  {left} s left")
            time.sleep(1)
        time.sleep(0.05)
    rec.set("pause", f"{rec.session}-pause-done")


def main():
    parser = argparse.ArgumentParser(description="Record labeled swing data with the Double Motor.")
    parser.add_argument("--swings", type=int, default=30, help="number of beeps (default 30)")
    parser.add_argument("--idle", type=int, default=60, help="seconds of moving around (default 60)")
    parser.add_argument("--still", type=int, default=10, help="seconds holding still (default 10)")
    args = parser.parse_args()

    dm = le.DoubleMotor()
    print("Searching for the Double Motor...")
    dm.connect(device_notification_delay=20)
    if not dm.connected:
        print("Could not connect.")
        return
    print("Connected!")
    dm.light_color(le.LEGO_COLOR_GREEN)

    session = time.strftime("%Y%m%d-%H%M%S")
    rec = Recorder(dm, session)
    try:
        if args.swings > 0:
            swing_round(dm, rec, args.swings)
        if args.idle + args.still > 0:
            idle_round(rec, args.idle, args.still)
    except KeyboardInterrupt:
        print("\nStopped early - saving what was recorded.")
    finally:
        rec.stop()
        dm.disconnect()

    new_file = not os.path.exists(DATA_FILE)
    with open(DATA_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(COLUMNS)
        w.writerows(rec.rows)
    secs = (float(rec.rows[-1][1]) - float(rec.rows[0][1])) if rec.rows else 0
    print(f"\nSaved {len(rec.rows)} readings ({len(rec.rows) / max(secs, 1e-9):.0f}/s) "
          f"from session {session} to {DATA_FILE}")


if __name__ == "__main__":
    main()
