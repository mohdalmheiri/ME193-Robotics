"""Find a loose sensor wire: live readings while you wiggle each wire in turn.

    python wire_test.py                  (wires VCC, GND, SCL, SDA)
    python wire_test.py SDA SCL          (only these)

With the Step Recorder running on the board, this starts a throwaway trial
(person "WireTest"), streams its samples as the board writes them, and walks
you through the wires: a few seconds hands off, then 10 s of wiggling each
one. At the end it discards the trial, so no file or row is left behind.

Each kind of bad contact looks different, because the sketch sets up the
MPU-6050 only once, at power-up:

- FAILED READS: every channel reads -1 (raw). The sensor didn't answer, and
  the readings come back when the contact does. A flickering SDA or SCL
  (data or clock) wire.
- ZEROS: every channel reads exactly 0, and stays 0. The MPU lost power for
  a moment and restarted asleep. A flickering VCC or GND wire.
- NO DATA: no samples at all. The sketch is stuck waiting on a jammed I2C
  bus (a data line touching GND or another wire, for example).
- BOARD RESTARTED: the connection to the board drops. Its power dipped,
  most likely VCC touching GND (a short), which also resets the sensor.

None of the last three recover by themselves. For ZEROS and NO DATA the test
restarts the app (its sketch wakes the sensor again, no power-cycle needed);
after a board restart it waits for the board to come back. Then it carries
on with the wires still to test.
"""
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

# Same board connection as sync_from_board.py: the ArduinoApps kit's deploy.py
KIT_TOOLS = Path.home() / "Documents" / "GitHub" / "ArduinoApps" / "tools"
APP_DIR = "/home/arduino/ArduinoApps/step-recorder"
REMOTE_DIR = f"{APP_DIR}/python/recordings"
sys.path.insert(0, str(KIT_TOOLS))
import deploy  # noqa: E402  (needs the line above to be found)

WIRES = ["VCC", "GND", "SCL", "SDA"]
PERSON = "WireTest"     # the throwaway trials' person, so they can't be mixed up with real ones
BASELINE_S = 5          # hands off first, to see what normal looks like
WIGGLE_S = 10           # then this long per wire
LINE_S = 0.25           # one printed line per this many seconds
NO_DATA_S = 0.6         # the board sends ~10 batches a second; this long with none = stuck
BOOT_WAIT_S = 180       # how long a restarting board gets to come back
FAILED = (-1 / 2048, -1 / 16.4)   # a failed read (-1 raw) after the sketch's scaling

RED, GREEN, YELLOW, BOLD, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m"


# ---- Talking to the board ------------------------------------------------------------
def board_command(board, command, timeout=20):
    """Run a short command on the board and return its output ('' if it didn't answer)."""
    r = deploy.remote(board, command, check=False, quiet=True, timeout=timeout)
    return r.stdout.decode().strip() if r is not None and r.stdout else ""


def app_answers(board):
    return '"app":"Step Recorder"' in board_command(board, "curl -s -m 2 localhost:7000/status", timeout=10)


def wait_for_app(board, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if app_answers(board):
            return True
        time.sleep(3)
    return False


def restart_app(board):
    """Restart the Step Recorder (the sketch's setup wakes the sensor again).
    Uploading the sketch fails now and then, so try twice."""
    board_command(board, f"arduino-app-cli app stop {APP_DIR}", timeout=60)
    for _ in range(2):
        if "started successfully" in board_command(board, f"arduino-app-cli app start {APP_DIR} 2>&1", timeout=180):
            break
    return wait_for_app(board, 60)


def remove_leftovers(board):
    """A board restart mid-test leaves its WireTest file behind (never saved,
    so it has no row in trials.csv). Delete those, and only those."""
    board_command(board, f"rm -f {REMOTE_DIR}/{PERSON}_*.csv")


def start_trial(board):
    """Start the throwaway trial and stream it. Returns (file name, process, rows)."""
    started = board_command(board, f'curl -s "localhost:7000/start?person={PERSON}&activity=Test"')
    if '"ok":true' not in started:
        sys.exit(f"Couldn't start the test trial: {started}")
    name = started.split('"file":"')[1].split('"')[0]
    rows = queue.Queue()
    proc = stream(board, f"{REMOTE_DIR}/{name}", rows)
    time.sleep(1.5)     # let the stream get going, then drop what came in so far
    while not rows.empty():   # (the first sample after a restart can be a leftover 0)
        rows.get()
    return name, proc, rows


def end_trial(board, name, proc):
    proc.terminate()
    board_command(board, "curl -s localhost:7000/stop; curl -s localhost:7000/discard")
    remove_leftovers(board)


def stream(board, path, rows):
    """Follow the trial's CSV on the board, putting each sample row in rows."""
    kind, target = board
    follow = f"tail -n +2 -F {path} 2>/dev/null"
    cmd = (["adb", "shell", follow] if kind == "adb" else
           # keepalives: notice within a few seconds if the board goes away
           ["ssh", *deploy.SSH_OPTS, "-o", "ServerAliveInterval=1", "-o", "ServerAliveCountMax=3", target, follow])
    # stdin=DEVNULL: otherwise ssh reads the keyboard and swallows the Enter presses
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)

    def read():
        for line in proc.stdout:
            parts = line.strip().split(",")
            if len(parts) >= 7:
                try:
                    rows.put([float(v) for v in parts[1:7]])
                except ValueError:
                    pass
    threading.Thread(target=read, daemon=True).start()
    return proc


# ---- Watching the readings -------------------------------------------------------------
def kind_of(sample):
    """'ok', 'failed' (-1 raw on every channel) or 'zero' (exactly 0 on every channel)."""
    if all(v == 0 for v in sample):
        return "zero"
    if all(abs(v - FAILED[0]) < 1e-4 for v in sample[:3]) and all(abs(v - FAILED[1]) < 1e-3 for v in sample[3:]):
        return "failed"
    return "ok"


def watch(rows, proc, label, seconds):
    """Print live readings for this many seconds. Returns the counts and None,
    or 'sensor' (zeros / no data: restart the app) or 'board' (it restarted)."""
    counts = {"ok": 0, "failed": 0, "zero": 0, "no_data_s": 0.0, "board": False}
    start = last_data = time.time()
    end = start + seconds
    while time.time() < end:
        line_end = time.time() + LINE_S
        got = {"ok": 0, "failed": 0, "zero": 0}
        mags = []
        while time.time() < line_end:
            try:
                s = rows.get(timeout=0.05)
            except queue.Empty:
                continue
            last_data = time.time()
            k = kind_of(s)
            got[k] += 1
            if k == "ok":
                mags.append(sum(v * v for v in s[:3]) ** 0.5)
        for k in got:
            counts[k] += got[k]
        quiet = time.time() - last_data
        t = time.time() - start

        if proc.poll() is not None:
            counts["board"] = True
            print(f"  {label:>9} {t:5.1f} s  {RED}{BOLD}BOARD RESTARTED: the connection dropped "
                  f"(power dip: VCC touching GND?){RESET}", flush=True)
            return counts, "board"
        if quiet > NO_DATA_S:
            counts["no_data_s"] += LINE_S
            status = f"{RED}{BOLD}NO DATA for {quiet:.1f} s (sketch stuck: jammed bus){RESET}"
        elif got["zero"]:
            status = f"{RED}{BOLD}ZEROS x{got['zero']} (sensor lost power: VCC/GND){RESET}"
        elif got["failed"]:
            status = f"{RED}{BOLD}FAILED READS x{got['failed']} (data/clock contact: SDA/SCL){RESET}"
        elif mags:
            g = sum(mags) / len(mags)
            status = f"{GREEN}ok{RESET}  {g:5.2f} g  " + "#" * min(40, round(g * 10))
        else:
            status = f"{YELLOW}waiting for the next batch{RESET}"
        print(f"  {label:>9} {t:5.1f} s  {status}", flush=True)

        # Stuck for good: no data well past a hiccup, or asleep (only zeros) for a while
        if quiet > 3 or (got["zero"] and not got["ok"] and counts["zero"] >= 50):
            return counts, "sensor"
    return counts, None


# ---- The test ------------------------------------------------------------------------------
def main():
    wires = sys.argv[1:] or WIRES
    board = deploy.find_board()
    status = board_command(board, "curl -s localhost:7000/status")
    if '"app":"Step Recorder"' not in status:
        sys.exit("The Step Recorder isn't answering on the board. Is it running?")
    if '"mode":"idle"' not in status:
        sys.exit("The Step Recorder is in the middle of a trial: finish it on the phone first.")
    remove_leftovers(board)

    name, proc, rows = start_trial(board)
    print(f"Streaming live readings from the board (throwaway trial {name})\n")
    steps = ["hands off"] + wires
    results, recovered_untouched = [], False
    try:
        while steps:
            label = steps[0]
            if label == "hands off":
                print(f"{BOLD}Hands off for {BASELINE_S} s: this is what normal looks like.{RESET}")
            else:
                input(f"\n{BOLD}Next: {label}.{RESET} Hold it near the sensor end, press Enter, then wiggle "
                      f"it for {WIGGLE_S} s (press it, bend it, tug it gently)...")
                while not rows.empty():     # what came in while waiting for Enter isn't this wire's
                    rows.get()
            counts, stopped = watch(rows, proc, label, BASELINE_S if label == "hands off" else WIGGLE_S)
            results.append((label, counts))
            steps.pop(0)
            if not stopped:
                continue

            # It won't come back by itself: get the board and sensor going again
            if label == "hands off":
                if recovered_untouched:
                    sys.exit("It stopped again without touching anything: a wire (most likely VCC or "
                             "GND) is fully off. Check the connections by eye first.")
                recovered_untouched = True
                steps.insert(0, "hands off")     # check it works before testing more wires
            proc.terminate()
            rest = f" with {', '.join(steps)}" if steps else ""
            if stopped == "board":
                print(f"\n{BOLD}Let go of the wires. Waiting for the board to start up again "
                      f"(up to {BOOT_WAIT_S // 60} min), then carrying on{rest}...{RESET}")
                if not wait_for_app(board, BOOT_WAIT_S):
                    sys.exit("The board didn't come back. Power-cycle it, wait for the address to scroll, "
                             f"then: python wire_test.py {' '.join(w for w in steps if w != 'hands off')}")
                remove_leftovers(board)
            else:
                end_trial(board, name, proc)
                input(f"\n{BOLD}The sensor stopped. Let go of the wires, then press Enter to restart the "
                      f"app (about 30 s) and carry on{rest}...{RESET}")
                if not restart_app(board):
                    sys.exit("The app didn't come back. Power-cycle the board, wait for the address to "
                             f"scroll, then: python wire_test.py {' '.join(w for w in steps if w != 'hands off')}")
            name, proc, rows = start_trial(board)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    finally:
        end_trial(board, name, proc)
        print(f"(discarded {name}: nothing left on the board)")

    print(f"\n{BOLD}Summary{RESET}  (samples: ok / failed reads / zeros, then seconds with no data)")
    for label, c in results:
        bad = c["failed"] or c["zero"] or c["no_data_s"] or c["board"]
        mark = f"{RED}<-- this one{RESET}" if bad and label != "hands off" else ""
        board_note = "  BOARD RESTARTED" if c["board"] else ""
        print(f"  {label:>9}: {c['ok']:5d} / {c['failed']:4d} / {c['zero']:4d}, "
              f"{c['no_data_s']:4.1f} s{board_note}  {mark}")


if __name__ == "__main__":
    main()
