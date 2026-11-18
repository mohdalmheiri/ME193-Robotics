# 🧭 Nolop Navigator (board app)

The UNO Q app for HW9. It reads both sensors, counts steps and turns, saves each walk and
serves the phone page, all on the board. No laptop or internet is needed on the walk.

**Status:** `app.yaml` and the phone page (`assets/index.html`) exist. The board code
(`python/`, `sketch/`) is next; the build order is at the end.

## How the phone and the board talk

The phone page does the labeling: it knows which button was pressed. The board does the
sensing: it knows the steps and turns. They talk over three web addresses.

**1. `GET /api/state`: "what are the numbers now?"** The page asks 4 times a second. The
board answers with its running totals:

```json
{"steps": 42.6, "distance_m": 29.8, "turns_left": 1, "turns_right": 0,
 "steps_at_last_turn": 30.2, "distance_at_last_turn": 21.1,
 "heading_deg": 85, "on_stairs": false}
```

Decimals are fine; the page rounds steps down and works out "steps since the turn" itself.

**2. `GET /api/reset?walker=Raph&kind=demo`: "a new walk starts now."** The board sets every
count to 0, picks the next walk number, and answers `{"ok": true, "walk": 3}`. The page
doesn't start the walk until it gets this answer. The walk number goes on every row of the
walk, so the board knows which file each row belongs to. (The phone can't number the walks
itself: its counter starts over whenever the page reloads, and each phone has its own.)

**3. `POST /api/rows`: "here are rows to save."** Whenever a row is saved (one per step,
plus one per button tap), the page puts it in a **waiting line** on the phone and sends
the line to the board:

```json
{"items": [
  {"session": "k3x9", "seq": 1, "row": {"walk": 3, "walker": "Raph", "kind": "demo", "steps": 1, "label": "Straight", "...": "..."}},
  {"session": "k3x9", "seq": 2, "row": {"walk": 3, "walker": "Raph", "kind": "demo", "steps": 2, "label": "Straight", "...": "..."}}
]}
```

The board saves them and answers `{"ok": true}`. Only then do they leave the line. If the
board doesn't answer, they stay on the phone and are sent again a quarter-second later, in
the same order. So the board must handle getting the same row twice. That's what the
**ticket** is for:

- **Ticket** = `session` (a random name the page picks each time it opens) + `seq` (a
  number that goes up by 1 for every message). The board remembers the highest `seq` it
  has handled for each session and **skips anything not higher**. Then a row sent twice
  (because the board's "ok" got lost on the way back) is saved once.
- **Undo** is a message in the same line, with its own ticket: `{"session": "k3x9", "seq": 41,
  "undo": 40}` means "remove the row whose seq was 40". If the row hadn't been sent yet, the
  page just drops it from the line instead, and no undo is sent. An undo for a row the board
  never got is harmless: there's nothing to remove.
- Every request must be answered within **1.5 s**, or the page counts it as failed and
  tries again.

## One walk, start to end

Raph records a demo walk; it's the third walk on this board.

| # | What happens | Phone → board | Board → phone |
|---|---|---|---|
| 1 | Raph picks **Raph**, **Live**, presses **Start walk** | `GET /api/reset?walker=Raph&kind=demo` | Zeroes the counts, starts walk 3: `{"ok": true, "walk": 3}` |
| 2 | The page says "Recording walk 3" and asks for numbers 4×/s | `GET /api/state` | `{"steps": 0.4, ...}` |
| 3 | Steps reach 1: the page saves a row, ticket seq 1 | `POST /api/rows` with seq 1 | Appends it to walk 3's CSV: `{"ok": true}` |
| 4 | … one row per step, seq 2, 3, … 24 | (same) | (same) |
| 5 | Raph taps **Left** before the corner: a row labeled Left, seq 25 | `POST /api/rows` with seq 25 | saved |
| 6 | The board's waist gyro sees the turn | — | `/api/state` now says `turns_left: 1, steps_at_last_turn: 26.1, distance_at_last_turn: 18.3`; the page's label goes back to Straight |
| 7 | The hotspot hiccups for 2 s: rows seq 30-33 wait on the phone; the page shows a red warning | (requests fail) | — |
| 8 | The board answers again: the waiting rows go in one batch, in order | `POST /api/rows` with seq 30-33 | saved, `{"ok": true}`; the warning clears |
| 9 | That "ok" is lost on the way back, so the page sends seq 30-33 again | `POST /api/rows` with seq 30-33 | All already handled: skipped, `{"ok": true}` |
| 10 | Raph taps **Stairs** by mistake (seq 40, already sent), then **Undo** | `POST /api/rows` with `{"seq": 41, "undo": 40}` | Removes row 40 from walk 3's CSV |
| 11 | At Nolop: **Arrived**, then **End walk** | the last rows | saved; the page says "all sent to the board" |

## Build order: the minimum for the first real walk

Each step can be tested on its own before the next. The simplest version first; better
versions later.

### Step 0: can the ankle sensor alone count turns? (before building anything)

**Why:** if the ankle sensor can count turns, we don't need the waist sensor or the long
wire at all: the hardware for the first walk is exactly HW7's. Raph's old recording
already showed 180° turnarounds clearly at the ankle (`docs/process_log.md`, 2026-11-17
test). Step 0 checks what that walk couldn't: **90° corners while walking**, **left vs
right**, a longer route, and both walkers.

**Setup.** Board and one MPU-6050 strapped to the right lower leg, near the ankle, with
the short wire, exactly as in HW7. **No new code:** HW7's Step Recorder app already saves
the raw ankle readings at 100 per second. Use its **Test** activity.

**The walk** (a few minutes, once by Mohammed and once by Raph):
1. Press **Start**, then **stand still for 5 s**. This is when the gyro's bias (its false
   turning rate when still) is measured.
2. Walk a loop that comes back to the start with **four left corners** (for example
   around a block or a corridor loop, anticlockwise).
3. Walk the same loop the other way: **four right corners**.
4. Two turns on the spot (one left, one right), then stand still 5 s and press **Stop**.
5. Write down the order of the turns.

**Check:** run `training/ankle_turn_check.py <recording>.csv` and look at the heading plot.
- **Readings drop out?** The script prints the gaps over 25 ms; HW7's page also warns
  about bad readings. Should be none (short wire).
- **Every corner a clear step?** The heading should be flat on the straight stretches and
  climb (or drop) at each corner, one step per corner, without guessing which is which.
- **Left vs right:** left corners should go one way and right corners the other.
- **Size:** each loop should add up to about 360° (each corner about 90°). Raph's
  turnarounds read about 13% low, so about 310-320° per loop would match that; much less
  would mean corners get lost.
- **Margin for the turn rule:** note the biggest heading change within any 2 s on the
  straight stretches and at the corners. On HW7's straight walks the wobble stayed under
  20° in 2 s, and Raph's turnarounds climbed 118-169° in 2 s. If corners climb well over
  60° in 2 s and straights stay well under it, ">60° within 2 s" is a safe rule.
- **How long each corner takes:** a 90° corner taken while walking may take longer than
  2 s. Measure how long each corner's climb lasts, from where the heading leaves the flat
  part to where it is flat again. **If corners take longer than 2 s, widen the turn window
  to 3 s; don't lower the 60° threshold.** A lower threshold lets the walking wobble look
  like a turn, while a wider window still keeps it out: on HW7's straight walks the wobble
  stayed under 27° within 3 s.
- **Pass:** all of the above for both walkers. Then the waist sensor and the long wire are
  dropped from the plan.

**Backup if the ankle fails: the two-sensor test.** Wire a second MPU-6050 for the waist
at 0x69 (AD0 to 3.3 V) on the long wire, record both with a copy of HW7's sketch that
reads both, and walk the same loops. Check (a) dropouts: rows where all six channels read
0 (lost power) or −1 (no answer), or gaps over 10 ms; zero allowed, including while
wiggling the wire; and (b) turns in the waist gyro, the same heading plot as above
(the script finds "up" itself, so a tilted sensor on the belt is fine). If the waist fails
too, rethink before building the app.

### Steps 1-9: the board app

| # | Piece | Simplest version | Test |
|---|---|---|---|
| 1 | Serve the page | `python/main.py` with the `web_ui` brick, nothing else | Phone opens the page; Mock mode works |
| 2 | Board address on the LED matrix | Reuse HW7's address service and scrolling code. The service writes only to the Step Recorder's folder, so add a second output file in this app's folder | Address scrolls on the matrix on the hotspot |
| 3 | Read the ankle sensor | HW7's `sketch.ino` as is (one MPU-6050 at 0x68, 100 Hz, with its reconnect fix) | Samples arrive in Python |
| 4 | Count steps and meters | HW7's `step_counter.py` + `step_model.npz`, unchanged | Walk 20 counted steps; the count is close |
| 5 | `GET /api/state` | The real `steps` and `distance_m`; every other field fixed at 0 / false | The page in Live mode shows steps going up |
| 6 | `GET /api/reset` | Zero the counts; walk number = highest walk number among saved files + 1 (as HW7 numbers trials) | Start walk works; the walk number goes up each time |
| 7 | `POST /api/rows` | Keep each walk's rows in memory as a list (with their seq), skip seqs already handled, remove a row on undo, then rewrite that walk's whole CSV and answer ok (a walk is only ~1000 rows) | A straight walk ends with a CSV on the board matching the phone's download |
| 8 | *Only if Step 0 fails:* read the waist sensor | Add the second MPU-6050 at 0x69 to the sketch (the backup test's sketch already does this) | Both read on a real walk (the long wire especially) |
| 9 | Count turns (ankle sensor) | The method of `training/ankle_turn_check.py`, running live: **measure the gyro bias while the walker stands still for 5 s right after `/api/reset`** (before the first step) and subtract it from then on; find "up" from the accelerometer averaged over 1 s; add up the turning rate around "up" to get the heading. A turn = the heading changes by more than 60° within 2 s (the starting guess, checked in Step 0), then a pause before the next one can count; its sign says left or right. Fill `turns_left/right`, both "at last turn" values and `heading_deg` | Turn on the spot and around corners; every turn counted once, left and right right |

After step 7 a straight walk can be recorded from start to end. After step 9 the first
real route walk can be recorded.

**Not needed for the first walk:** the stairs classifier (`on_stairs` stays false), running
the policy on the board (the first walks are demos), and MQTT. One known gap in the simple
version of step 7: if the board app restarts, it forgets which seqs it handled, so a
batch sent again right after a restart could be saved twice. Fine to start with; fix
later by saving the last seq to a file.

## How to deploy

Like HW7: a symlink in the ArduinoApps kit points to this folder, then
`python3 tools/deploy.py <app name>`. Only one app runs at a time, so sharing port 7000
with HW7's Step Recorder is fine.
