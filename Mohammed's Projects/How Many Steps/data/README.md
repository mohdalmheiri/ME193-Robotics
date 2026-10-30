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
| `phone_raw/` | phyphox exports, one zip per trial, named to match the ankle file |
| `trials.csv` | One row per trial with the real counts (copied from the board) |
| `sync_from_board.py` | Copies `raw/` and `trials.csv` from the board, then lists anything missing |

## File names

Every trial is `Person_Activity_Tnn`, for example `Mohammed_Walk_normal_T03`:

- `raw/Mohammed_Walk_normal_T03.csv` from the ankle
- `phone_raw/Mohammed_Walk_normal_T03.zip` from the phone

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

## trials.csv

| Column | Meaning |
|---|---|
| `file` | the ankle CSV's name |
| `person`, `activity` | as in the file name |
| `steps` | steps counted by hand (both feet), entered on the phone after the trial |
| `distance_m` | meters covered (20 by default; 0 for Stand, Fidget, LegSwing; from GPS or the phone for Outdoor) |
| `duration_s` | length of the ankle recording, from its number of samples |

For `Outdoor`, `steps` is the phone's step count, since nobody counts a long walk by hand.

## Phone recordings (`phone_raw/`)

phyphox's built-in experiments use one sensor at a time. To get the accelerometer and
gyroscope together, make your own **simple experiment** with the **+** button on
phyphox's main screen:

- **Ankle trial**: Accelerometer (with g) and Gyroscope, rate 100 Hz (to match the ankle;
  phyphox averages faster readings down to it, 0 would mean as fast as possible)
- **Ankle trial GPS**: the same, plus Location, for the `Outdoor` walk only

After a trial, export with **⋮ → Export Data → CSV (Comma, decimal point)**, and only then
clear the data for the next trial (pressing ▶ again would add to the old recording). phyphox makes
a zip with one CSV per sensor (time in s from the start, then the x, y, z values;
acceleration in m/s², rotation in rad/s) and a `meta/` folder whose `time.csv` holds the
phone's clock time at Start. Save the zip with the trial's name. The exact menu labels
can differ a little between phyphox versions and iPhone/Android.

`Outdoor` zips contain GPS positions of the walk, so `.gitignore` keeps them off GitHub.

## Lining up ankle and phone: the stomp

Every trial starts with **one hard stomp** of the ankle leg after both recordings are
running. It shows up as a sharp spike in the ankle's acceleration and in the phone's at
the same moment, so the two recordings can be lined up to the sample later. The clocks
alone (board in UTC, phone in its own time) can be off by a second or more. Stand still
for a moment before and after the stomp so the spike is easy to find.
