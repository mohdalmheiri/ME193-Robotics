# Data

Counted trials for training and testing the step counter. Each trial is recorded twice at
the same time: by the ankle IMU (the UNO Q's Step Recorder app) and by a phone in a
pocket (phyphox). For the step-by-step routine during recording, see
[`RECORDING_CHECKLIST.md`](RECORDING_CHECKLIST.md).

## How the trials are recorded

Recorded alone (no helper) in a hallway, with two phones:

- **Phone 1, in the pocket:** runs phyphox only. Always the same phone, the same pocket
  and the same direction, so the phone data stays comparable across trials. Auto-Lock is
  set to Never during the session, because phyphox stops recording when the screen
  locks, and turned back on afterwards.
- **Phone 2, in the hand:** runs the Personal Hotspot the board joins, and the Step
  Recorder page (Start, Stop, entering the count).

Each walking or running trial is **one way along the 20 m course**: a stomp at the start
line, then walk or run to the finish line while counting steps silently (every foot
that lands, both feet; the stomp doesn't count). Stand, Fidget and LegSwing stay in place.

For about 5 trials across the paces, Phone 2 screen-records while the Camera app shows
the feet, so the hand counts can be checked afterwards. The recording starts on the Step
Recorder page, so each video shows which trial it is. The videos stay on the phone and
off GitHub.

| Path | What it holds |
|---|---|
| `raw/` | Ankle recordings, one CSV per trial, copied from the board by `sync_from_board.py` |
| `phone_raw/` | phyphox recordings: one folder per trial (e.g. `Mohammed_Walk_slow_T02/`), and the exports as phyphox named them in `original_zips/` |
| `trials.csv` | One row per trial with the real counts (copied from the board) |
| `real_durations.csv` | The real length of each ankle recording (see below) |
| `excluded_trials.csv` | Trials left out of training, with the reason (see below) |
| `sync_from_board.py` | Copies `raw/` and `trials.csv` from the board, then lists anything missing |
| `check_recordings.py` | Matches ankle and phone recordings, checks them for damage (bad connection, cut short, sensor shifted on the leg; not judged for runs, whose speed-up turns the leg's swing axis anyway), finds the stomps, plots each trial to `../media/recording_checks/` |
| `wire_test.py` | Live sensor readings while you wiggle each wire in turn, to find a loose one |

## File names

Every trial is `Person_Activity_Tnn`, for example `Mohammed_Walk_normal_T03`:

- `raw/Mohammed_Walk_normal_T03.csv` from the ankle
- `phone_raw/Mohammed_Walk_normal_T03/` from the phone (its zip, unzipped)

The person comes first and never contains `_` (the board turns other characters into
`-`), and the trial number comes last, so a name splits cleanly even though some
activities contain `_`. Trial numbers count up separately for each person and activity.

| Activity | What to do |
|---|---|
| `Walk_slow`, `Walk_normal`, `Walk_fast`, `Run` | One way along the 20 m course at that pace |
| `Stand` | Stand still (0 steps, 0 m) |
| `Fidget` | Stand and shift your weight, without stepping (0 steps, 0 m) |
| `LegSwing` | Sit and swing the ankle leg (0 steps, 0 m) |
| `Test` | Counted test walks (one way, 20 m), kept for testing the finished model |
| `Outdoor` | The long walk, compared with the phone's own step counter |

## Ankle CSVs (`raw/`)

100 rows per second, same columns as HW6: `time` (UTC, ISO format), `ax ay az` (g),
`gx gy gz` (°/s), `activity`, `person`. The IMU is on the right lower leg, near the
ankle, as in HW6.

The `time` column assumes exactly 100 samples per second (start + n × 10 ms). The sketch
really samples a little slower, about 99.0-99.7 per second, because it waits at least
10 ms between readings and sometimes a bit more. All recordings use the same sketch, so
they stay consistent with each other. For exact timing, `real_durations.csv` has each
recording's real length: from its first row's time to the moment the board last wrote
the file (Stop), with the actual samples per second. `check_recordings.py` adds new
trials to it from the board, since the board would lose that time if a file there were
ever changed.

## trials.csv

| Column | Meaning |
|---|---|
| `file` | the ankle CSV's name |
| `person`, `activity` | as in the file name |
| `steps` | steps counted by hand (both feet), entered on the phone after the trial |
| `distance_m` | meters covered (20 by default; 0 for Stand, Fidget, LegSwing; from GPS or the phone for Outdoor) |
| `duration_s` | length of the ankle recording, from its number of samples |

For `Outdoor`, `steps` is the phone's step count, since nobody counts a long walk by hand.

If the board loses power right after a save, the row can be lost and leave NUL bytes in its
place (`trials.csv` has one such gap, just before `Mohammed_Run_T13`). The scripts skip
the NUL bytes when reading; the file itself stays as the board wrote it.

## excluded_trials.csv

Trials whose ankle recording is damaged (a loose sensor wire, a board crash) stay in
`raw/` and `trials.csv` as they were recorded, and are listed here instead, one row per
file with the `reason`. Training leaves them out. A file in `raw/` that never got a row in
`trials.csv` (the board stopped mid-trial) is listed too, so every bad file is accounted
for. `check_recordings.py` marks these trials, counts what's left for training per
activity, and lists any trial with problems that isn't excluded yet.

## Phone recordings (`phone_raw/`)

phyphox's built-in experiments use one sensor at a time. To get the accelerometer and
gyroscope together, make your own **simple experiment** with the **+** button on
phyphox's main screen:

- **Steps - Motion**: Accelerometer (with g) and Gyroscope, rate 100 Hz (to match the
  ankle; phyphox averages faster readings down to it, 0 would mean as fast as possible)
- **Steps - GPS**: the same, plus Location, for the `Outdoor` walk only

After a trial, export with **⋮ → Export Data → CSV (Comma, decimal point)**, and only then
clear the data for the next trial (pressing ▶ again would add to the old recording). The
exact menu labels can differ a little between phyphox versions and iPhone/Android.

phyphox names each zip after the experiment and the export time
(`Steps - Motion 2026-10-31 16-59-36.zip`). Inside are one CSV per sensor (time in s from
the start, then x, y, z; acceleration in m/s², rotation in rad/s) and a `meta/` folder
whose `time.csv` holds the phone's clock time at Start. The layout of `phone_raw/`:

```
phone_raw/
├── original_zips/             the exports exactly as phyphox named them, kept untouched
│   └── Steps - Motion 2026-10-31 16-59-36.zip
└── Mohammed_Walk_slow_T02/    that zip, unzipped, named after its trial
    ├── Accelerometer.csv
    ├── Gyroscope.csv
    └── meta/                  device.csv, time.csv
```

Each zip is unzipped once, straight into its trial's folder; there are no other copies.
Which zip belongs to which trial comes from the start times: `check_recordings.py` works
it out, says where to unzip any zip that isn't unzipped yet, and confirms that every trial
folder starts when its trial does.

`Outdoor` recordings contain GPS positions of the walk, so `.gitignore` keeps them off
GitHub: trial folders named `..._Outdoor_Tnn`, and zips whose name contains "GPS" (the
title of the GPS experiment). `check_recordings.py` warns if any recording with GPS data
isn't covered.

## Lining up ankle and phone: the stomp

Every trial starts with **one hard stomp** of the ankle leg after both recordings are
running. It shows up as a sharp spike in the ankle's acceleration and in the phone's at
the same moment, so the two recordings can be lined up to the sample later. The clocks
alone (board in UTC, phone in its own time) can be off by a second or more. Stand still
for a moment before and after the stomp so the spike is easy to find.
