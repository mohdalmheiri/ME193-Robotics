"""Check the recorded trials for damage and line up the ankle and phone recordings.

    python check_recordings.py            (from this folder; reads only, changes nothing)

For every trial in trials.csv:

1. Finds its phone recording: each phyphox export unzipped into its own folder
   in phone_raw/. They are matched by start time (meta/time.csv on the phone,
   the first row's time on the ankle), and the order must agree. A folder
   named after the trial (a copy, e.g. Mohammed_Walk_slow_T02/) counts as the
   same recording as the original it was copied from, and must match it.
2. Checks the ankle recording for signs of a bad connection (see check_ankle):
   missing samples, frozen or zero readings, readings stuck at the sensor's
   maximum, and one-sample glitches.
3. Finds the stomp at the start, in the ankle and in the phone recording.
4. Saves one plot per trial to ../media/recording_checks/.

The ankle CSV's time column can't show missing samples: the board writes
start + n x 10 ms, whatever really happened. So the real length of each
recording is taken from the board instead: the time its file was last written
(= Stop) minus the first row's time. If samples were lost or the sensor
slowed down, there are fewer samples than that real length x 100. The board
forgets that time if a file there is ever touched, so the first time a trial
is checked, its real length is saved to real_durations.csv and read from
there afterwards (the only file this script writes, besides the plots).
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save figures to files, don't open windows
import matplotlib.pyplot as plt
import numpy as np

DATA = Path(__file__).resolve().parent
RAW = DATA / "raw"
PHONE = DATA / "phone_raw"
PLOTS = DATA.parent / "media" / "recording_checks"
REAL_LENGTHS = DATA / "real_durations.csv"
REAL_COLUMNS = ["file", "samples", "start_utc", "end_utc", "real_s", "samples_per_s"]
KIT_TOOLS = Path.home() / "Documents" / "GitHub" / "ArduinoApps" / "tools"
REMOTE_DIR = "/home/arduino/ArduinoApps/step-recorder/python/recordings"

RATE = 100                       # ankle samples per second
G = 9.81                         # phyphox gives m/s^2; divide by this for g
CHANNELS = ["ax", "ay", "az", "gx", "gy", "gz"]

# The MPU-6050's limits at the sketch's settings (+/-16 g, +/-2000 deg/s):
# the largest raw reading, 32767, divided by the sketch's scale factors
ACC_MAX = 32767 / 2048           # 16.0 g
GYRO_MAX = 32767 / 16.4          # 1998 deg/s
# What a failed I2C read turns into: 0xFFFF = -1 raw -> -1/2048 g, -1/16.4 deg/s
FAILED_READ = (-1 / 2048, -1 / 16.4)

FROZEN_SAMPLES = 20              # 0.2 s of identical readings on all 6 channels = frozen sensor
GLITCH_ACC = 2.0                 # g: a lone sample this far from both neighbours...
GLITCH_GYRO = 300.0              # deg/s: ...while the neighbours agree = a glitch, not movement
STOMP_SEARCH_S = 15              # look for the stomp in the first 15 s of the ankle recording
STOMP_MIN_G = 2.0                # the stomp must reach |a| >= 1 g + this...
STOMP_DOMINANCE = 2.0            # ...and be this many times bigger than any step that follows
STOMP_CLOCK_S = 0.5              # the phone's stomp must be within this of where the clocks put it
NEAR_STOMP_S = 0.1               # glitches/at-max readings this close to the stomp are the impact itself
SLOWEST_RATE = 98.5              # samples/s; the sketch normally runs at ~99.3 (it waits >= 10 ms per sample)


# ---- Loading ------------------------------------------------------------------
def load_ankle(name):
    with open(RAW / name, newline="") as f:
        rows = list(csv.DictReader(f))
    data = np.array([[float(r[c]) for c in CHANNELS] for r in rows])
    start = datetime.fromisoformat(rows[0]["time"]).timestamp()
    return data, start


def load_phone(folder):
    """Returns the phone's start (Unix time), the accelerometer and gyroscope
    arrays (time s, x, y, z) and the pause times, from one unzipped export."""
    def read(path):
        with open(path, newline="") as f:
            return np.array([[float(v) for v in row] for row in list(csv.reader(f))[1:]])
    with open(folder / "meta" / "time.csv", newline="") as f:
        events = list(csv.DictReader(f))
    start = float(next(e for e in events if e["event"] == "START")["system time"])
    pauses = [float(e["experiment time"]) for e in events if e["event"] == "PAUSE"]
    return {"start": start, "acc": read(folder / "Accelerometer.csv"),
            "gyro": read(folder / "Gyroscope.csv"), "pauses": pauses, "folder": folder.name}


def board_end_times():
    """When each recording was last written on the board (Unix time), via the
    deploy kit (same pinned connection as sync_from_board.py). {} if the
    board can't be reached; the duration check is then skipped."""
    try:
        sys.path.insert(0, str(KIT_TOOLS))
        import deploy
        board = deploy.find_board()
        r = deploy.remote(board, f"cd {REMOTE_DIR} && stat -c '%n %.6Y' *.csv",
                          check=False, quiet=True, timeout=20)
        lines = r.stdout.decode().split("\n") if r is not None and r.returncode == 0 else []
        return {name: float(t) for name, t in (l.split() for l in lines if l.strip())}
    except (Exception, SystemExit) as e:
        print(f"(board not reachable, skipping the duration check: {e})")
        return {}


def real_end_times(ankles):
    """The real end (Unix time) of each ankle recording. Saved ones come from
    real_durations.csv; any trial not in it yet is asked from the board and
    added to the file, so it's kept even if the board's copy changes later."""
    saved = {}
    if REAL_LENGTHS.exists():
        with open(REAL_LENGTHS, newline="") as f:
            saved = {r["file"]: r for r in csv.DictReader(f)}
    ends = {name: datetime.fromisoformat(r["end_utc"]).timestamp() for name, r in saved.items()}
    missing = [a for a in ankles if a[0]["file"] not in saved]
    if missing:
        from_board = board_end_times()
        new_rows = []
        for trial, data, start in missing:
            if trial["file"] in from_board:
                end = from_board[trial["file"]]
                ends[trial["file"]] = end
                new_rows.append({
                    "file": trial["file"], "samples": len(data),
                    "start_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
                    "end_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
                    "real_s": round(end - start, 3), "samples_per_s": round(len(data) / (end - start), 2)})
        if new_rows:
            new_file = not REAL_LENGTHS.exists()
            with open(REAL_LENGTHS, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=REAL_COLUMNS)
                if new_file:
                    writer.writeheader()
                writer.writerows(new_rows)
            print(f"Saved the real length of {len(new_rows)} new recordings to {REAL_LENGTHS.name}")
    return ends


def unique_phone_recordings(folders, trial_names):
    """One entry per phone recording. A trial-named copy and its original have
    the same start time; keep the trial-named one (it's what the checklist
    asks for) and remember the other folder names for the printout."""
    by_start = {}
    for phone in folders:
        by_start.setdefault(round(phone["start"], 3), []).append(phone)
    unique = []
    for group in by_start.values():
        group.sort(key=lambda p: p["folder"] not in trial_names)   # trial-named first
        keep = group[0]
        keep["copies"] = [p["folder"] for p in group[1:]]
        unique.append(keep)
    return sorted(unique, key=lambda p: p["start"])


# ---- 2. Signs of a bad connection --------------------------------------------------
def longest_run(mask):
    """Length of the longest stretch of True in a boolean array."""
    best = run = 0
    for m in mask:
        run = run + 1 if m else 0
        best = max(best, run)
    return best


def check_ankle(data, start, end_time, stomp_index):
    acc, gyro = data[:, :3], data[:, 3:]
    mag = np.linalg.norm(acc, axis=1)
    result = {"samples": len(data), "length_s": len(data) / RATE}

    # Missing or slow samples: compare the sample count with the real length
    if end_time is not None:
        real = end_time - start
        result["real_s"] = real
        result["rate"] = len(data) / real

    # Frozen sensor: all 6 channels exactly the same as the sample before
    same = np.all(np.diff(data, axis=0) == 0, axis=1)
    result["longest_frozen"] = longest_run(same) + (1 if same.any() else 0)

    # Zeros (a sleeping MPU reads 0) and failed reads (-1 raw on every channel)
    result["zero_rows"] = int(np.sum(np.all(data == 0, axis=1)))
    failed = np.all(np.isclose(acc, FAILED_READ[0]), axis=1) & np.all(np.isclose(gyro, FAILED_READ[1]), axis=1)
    result["failed_reads"] = int(np.sum(failed))

    # The stomp is a real impact that can briefly pass the sensor's range and
    # last only a sample or two, so readings right at the stomp are counted
    # separately from the rest of the recording
    near = np.zeros(len(data), bool)
    if stomp_index is not None:
        near[max(0, stomp_index - int(NEAR_STOMP_S * RATE)):stomp_index + int(NEAR_STOMP_S * RATE) + 1] = True

    # Stuck at the sensor's maximum
    at_max = np.any(np.abs(acc) >= ACC_MAX - 0.01, axis=1) | np.any(np.abs(gyro) >= GYRO_MAX - 1, axis=1)
    result["at_max"] = int(np.sum(at_max & ~near))
    result["at_max_stomp"] = int(np.sum(at_max & near))

    # One-sample glitches: a value far from both neighbours while the two
    # neighbours agree. Real movement (even the stomp) builds up over
    # several samples at 100 Hz; a bad contact flips a single reading.
    def glitches(x, limit):
        prev, here, nxt = x[:-2], x[1:-1], x[2:]
        found = np.zeros(len(x), bool)
        found[1:-1] = (np.abs(here - prev) > limit) & (np.abs(here - nxt) > limit) & (np.abs(prev - nxt) < limit / 4)
        return found
    glitch = np.zeros(len(data), bool)
    for i in range(3):
        glitch |= glitches(acc[:, i], GLITCH_ACC) | glitches(gyro[:, i], GLITCH_GYRO)
    result["glitches"] = int(np.sum(glitch & ~near))
    result["glitches_stomp"] = int(np.sum(glitch & near))

    # Gravity while still: should be ~1 g. A sensor that reset mid-recording
    # would come back at its default +/-2 g range and read ~8 g here.
    still = [mag[i:i + RATE] for i in range(0, len(mag) - RATE, RATE // 2)
             if np.std(mag[i:i + RATE]) < 0.02]
    result["still_gravity"] = (min(np.mean(w) for w in still), max(np.mean(w) for w in still)) if still else None
    result["peak_g"] = float(mag.max())
    return result


# ---- 3. The stomp -------------------------------------------------------------------
def find_stomp(t, mag, t_from, t_to, compare_to):
    """The stomp = the biggest |a| between t_from and t_to (s). Returns its
    index, time, height above 1 g, and how many times bigger it is than the
    biggest peak in the compare_to time range (the trial itself, after the
    stomp). For the phone that range leaves out putting it into and taking it
    out of the pocket, which shake it more than walking does."""
    window = (t >= t_from) & (t <= t_to)
    if not window.any():
        return None
    i = np.flatnonzero(window)[np.argmax(mag[window])]
    later = mag[(t > t[i] + 0.5) & (t >= compare_to[0]) & (t <= compare_to[1])]
    biggest_later = later.max() - 1 if len(later) else 0
    return {"i": int(i), "t": float(t[i]), "height": float(mag[i] - 1),
            # floor of 0.1 g: when nothing moves after the stomp (Stand), the
            # ratio would otherwise divide by almost nothing
            "vs_steps": float((mag[i] - 1) / max(biggest_later, 0.1))}


def stomp_is_clear(s):
    """Clear = a big spike that stands well above every step after it."""
    return s is not None and s["height"] >= STOMP_MIN_G and s["vs_steps"] >= STOMP_DOMINANCE


# ---- 4. Plot ---------------------------------------------------------------------------
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]   # x, y, z (and ankle, phone)


def plot_trial(trial, data, phone, stomp_ankle, offset, verdict):
    """Three panels on one time axis, 0 = the ankle's stomp:
    ankle acceleration, ankle rotation, and |acceleration| of ankle and phone."""
    t = np.arange(len(data)) / RATE - (stomp_ankle["t"] if stomp_ankle else 0)
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    for i, name in enumerate(["x", "y", "z"]):
        axes[0].plot(t, data[:, i], color=COLORS[i], lw=0.8, label=name)
        axes[1].plot(t, data[:, 3 + i], color=COLORS[i], lw=0.8, label=name)
    axes[0].set_ylabel("Ankle accel (g)")
    axes[1].set_ylabel("Ankle rotation (°/s)")
    axes[2].plot(t, np.linalg.norm(data[:, :3], axis=1), color=COLORS[0], lw=0.8, label="ankle")
    if phone is not None and offset is not None:
        # phone time -> the same axis: shift by where the phone's stomp is
        tp = phone["acc"][:, 0] - offset
        axes[2].plot(tp, np.linalg.norm(phone["acc"][:, 1:], axis=1) / G, color=COLORS[1], lw=0.8,
                     label="phone (pocket)")
        axes[2].set_xlim(min(t[0], tp[0]) - 1, max(t[-1], tp[-1]) + 1)
    axes[2].set_ylabel("|accel| (g)")
    axes[2].set_xlabel("Time from the stomp (s)")
    for ax in axes:
        ax.axvline(0, color="#7a7974", lw=1, ls=":")
        ax.grid(color="#ebeae6", lw=0.8)
        ax.legend(loc="upper right", frameon=False, ncol=3, fontsize=9)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_title(f"{trial['file'][:-4]}  ·  {trial['steps']} steps, {trial['distance_m']} m, "
                      f"{trial['duration_s']} s  ·  {verdict}", loc="left", fontsize=11)
    fig.tight_layout()
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOTS / f"{trial['file'][:-4]}.png", dpi=110)
    plt.close(fig)


# ---- Main -------------------------------------------------------------------------------
def main():
    with open(DATA / "trials.csv", newline="") as f:
        trials = list(csv.DictReader(f))
    trial_names = {t["file"][:-4] for t in trials}
    phones = unique_phone_recordings(
        [load_phone(d) for d in PHONE.iterdir() if (d / "meta" / "time.csv").exists()], trial_names)

    # 1. Match by start time: each ankle recording gets the phone recording that
    # started closest before it (phyphox is started first, then Start on the board)
    ankles = []
    for trial in trials:
        data, start = load_ankle(trial["file"])
        ankles.append((trial, data, start))
    ankles.sort(key=lambda a: a[2])
    ends = real_end_times(ankles)
    used, matches = set(), []
    for trial, data, start in ankles:
        before = [p for p in phones if p["start"] <= start + 5 and p["folder"] not in used]
        phone = max(before, key=lambda p: p["start"]) if before else None
        if phone and start - phone["start"] > 120:    # more than 2 min earlier: not this trial
            phone = None
        if phone:
            used.add(phone["folder"])
        matches.append((trial, data, start, phone))
    # The phone recordings must come in the same order as the ankle ones
    starts = [m[3]["start"] for m in matches if m[3]]
    order_ok = starts == sorted(starts)

    print(f"{len(trials)} ankle recordings, {len(phones)} phone recordings, "
          f"order {'agrees' if order_ok else 'DOES NOT agree'}")
    for p in phones:
        if p["folder"] not in used:
            print(f"  phone recording with no ankle trial: {p['folder']}")
    # A trial-named folder must be that trial's recording (not a mislabelled copy)
    for trial, _, _, phone in matches:
        name = trial["file"][:-4]
        if name in {p["folder"] for p in phones} and (phone is None or phone["folder"] != name):
            print(f"  phone_raw/{name}/ starts at a different time than trial {name}: wrong copy?")

    rows = []
    for trial, data, start, phone in matches:
        mag = np.linalg.norm(data[:, :3], axis=1)
        t = np.arange(len(data)) / RATE
        s_ankle = find_stomp(t, mag, 0, STOMP_SEARCH_S, (0, t[-1]))
        q = check_ankle(data, start, ends.get(trial["file"]), s_ankle["i"] if s_ankle else None)

        s_phone = offset = None
        if phone is not None and s_ankle is not None:
            # Where the stomp should be in the phone recording, from the two
            # clocks; then look within 3 s of that for the phone's own peak
            expected = start + s_ankle["t"] - phone["start"]
            ankle_end = start + t[-1] - phone["start"]    # the trial's end, in phone time
            tp = phone["acc"][:, 0]
            s_phone = find_stomp(tp, np.linalg.norm(phone["acc"][:, 1:], axis=1) / G,
                                 expected - 3, expected + 3, (expected, ankle_end - 1))
            if s_phone:
                offset = s_phone["t"]
                s_phone["clock"] = s_phone["t"] - expected   # phone clock minus board clock
        problems = []
        if q.get("rate", RATE) < SLOWEST_RATE:
            problems.append(f"only {q['rate']:.1f} samples/s")
        if q["longest_frozen"] >= FROZEN_SAMPLES:
            problems.append(f"frozen for {q['longest_frozen']} samples")
        for key, label in [("zero_rows", "zero rows"), ("failed_reads", "failed reads"),
                           ("at_max", "readings at max"), ("glitches", "glitches")]:
            if q[key]:
                problems.append(f"{q[key]} {label}")
        if q["still_gravity"] and not (0.9 < q["still_gravity"][0] and q["still_gravity"][1] < 1.1):
            problems.append("gravity off while still")
        if not stomp_is_clear(s_ankle):
            problems.append("ankle stomp unclear")
        if phone is not None and not (stomp_is_clear(s_phone) and abs(s_phone["clock"]) < STOMP_CLOCK_S):
            problems.append("phone stomp unclear")
        verdict = "OK" if not problems else "; ".join(problems)
        plot_trial(trial, data, phone, s_ankle, offset, verdict)
        rows.append((trial, q, phone, s_ankle, s_phone, start, verdict))

    # The printout: one block per trial
    for trial, q, phone, sa, sp, start, verdict in rows:
        print(f"\n{trial['file']}  ({trial['activity']}, {trial['steps']} steps)  ->  {verdict}")
        real = f", real length {q['real_s']:.2f} s -> {q['rate']:.1f} samples/s" if "real_s" in q else ""
        print(f"  ankle: {q['samples']} samples = {q['length_s']:.2f} s{real}")
        g = q["still_gravity"]
        print(f"         frozen max {q['longest_frozen']} samples, zeros {q['zero_rows']}, failed reads "
              f"{q['failed_reads']}, at max {q['at_max']} (+{q['at_max_stomp']} at the stomp), "
              f"glitches {q['glitches']} (+{q['glitches_stomp']} at the stomp), "
              f"peak {q['peak_g']:.1f} g, still gravity "
              + (f"{g[0]:.3f}-{g[1]:.3f} g" if g else "n/a"))
        if sa:
            print(f"  stomp ankle: at {sa['t']:.2f} s, {sa['height']:+.1f} g above 1 g, "
                  f"{sa['vs_steps']:.1f}x the biggest step after it")
        if phone:
            copies = f" (= {', '.join(phone['copies'])})" if phone["copies"] else ""
            print(f"  phone: {phone['folder']}{copies}, started {start - phone['start']:.1f} s before the ankle, "
                  f"{phone['acc'][-1, 0]:.1f} s long")
        if sp:
            print(f"  stomp phone: at {sp['t']:.2f} s, {sp['height']:+.1f} g above 1 g, "
                  f"{sp['vs_steps']:.1f}x the biggest step after it; phone clock vs board {sp['clock']:+.2f} s")
    print(f"\nPlots in {PLOTS.relative_to(DATA.parent)}/")


if __name__ == "__main__":
    main()
