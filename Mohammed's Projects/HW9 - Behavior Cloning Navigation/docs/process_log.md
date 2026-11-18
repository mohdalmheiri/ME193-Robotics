# HW9 process log

A running record of what was tried, what failed and what we figured out.

## 2026-11-17: Setup and first decisions

**Decided**
- Folder layout: `uno_q/` (board app), `training/`, `data/`, `docs/`, `media/`. The phone
  page lives in `uno_q/assets/` instead of a separate `ui/` folder, because the board
  serves its page from there. A second copy elsewhere would drift out of sync.
- Step counter: starting with Mohammed's HW7 counter, because it already runs on the
  board in plain numpy (no PyTorch, no laptop, no internet). To be confirmed with Raph.
  Raph's 1-D CNN counter is the alternative being compared. It currently runs on a
  laptop in PyTorch, so it would need its weights moved to numpy to run on the board.
- Policy: start with a lookup table (like the AnnaCode Table Cloner); try a small
  neural net only if needed.
- Phone link: the phone's hotspot, not the board as its own network, so the laptop can
  still reach the board to deploy.

**Checked**
- HW7's sensor was worn on the right lower leg, near the ankle, with the whole board
  strapped there. Its counter was trained only on Mohammed, only on straight 20 m walks
  (3.0% off live after the sensor-angle fix).
- Raph's counter misses about 1 step per turn. Here the count of steps since the last
  turn starts over at each turn, so a step missed right at a turn should matter less.

**Open**
- Start point and route; inside a building or across campus.
- Whether the waist sensor's long I2C wire reads reliably on a walk.
- Whether the HW7 counter holds up on Raph's walking and on turns (first checklist item).

## 2026-11-17: CSV columns and a known page bug

**Decided**
- The walk CSVs use exactly the columns the phone page exports: `walk, walker, kind,
  t_ms, steps, steps_since_turn, turns, turns_left, turns_right, heading_deg, on_stairs,
  label, predicted`. `data/README.md` explains each one.
- `kind` is `demo` or `dagger`. `predicted` is filled only on `dagger` rows.
- `heading_deg` is saved for checking only. It drifts, so the policy won't use it.

**Known bug (left in the page on purpose for now)**
- A `Left` or `Right` label can stay on for one step after the turn has ended.
- **To do: the label-cleanup script handles it.** Plan: once `turns` has gone up for
  that turn (the board has counted it), a `Left` or `Right` row whose `steps_since_turn`
  is already 1 or more becomes `Straight`. Rows *before* the turn is counted are the real
  turn label and are left alone (they also have `steps_since_turn` of 1 or more, so the
  `turns` check is what tells the two apart). Raw files stay unchanged; only the training
  copy is fixed.

## 2026-11-17: Reading the phone page, and the first page fixes

**How the page was checked:** read in full, then its script was run against a fake board
(macOS's built-in JavaScript engine, fake page elements, a board that can refuse, go
silent or answer late). All 20 checks passed after the fixes below. Not yet tried on a
real phone or the real board.

**Findings**
1. **Counts carried over between walks** (the serious one). Start walk set the page's
   numbers to 0, but a quarter-second later the board's running totals overwrote them, so
   walk 2 would start with walk 1's steps and turns. **It wasn't caught because Mock mode
   never asks the board for numbers**: in Mock, the page's own 0 is the only count, so the
   reset looked like it worked. Lesson: test Live, even against a fake board.
2. Data lived only in the phone's memory: a reload lost the walk, and a locked iPhone
   stops the page asking the board, so steps taken while locked get no rows.
3. The "can't reach the board" message only showed on the Record tab, never cleared, and
   the instruction kept showing as if nothing were wrong.
4. The page's walk counter starts over on every reload and on each phone.
5. The download is one file with every walk since the page opened.
6. Undo removes only the tap row; the step rows saved with the wrong label stay.
7. Left/Right switched back to Straight after a fixed 1.5 s, not when the turn ended:
   the likely cause of the turn label staying on for a step after the turn.
8. The HW7 counter's total has decimals (29.6), so the page would have saved a row at
   every update and "steps since the turn" would have had decimals.
9. Small: the title said "Campus Navigator" (app.yaml: "Nolop Navigator"), and a comment
   said the counter updates every 0.25 s (HW7's updates every 0.5 s).
10. Steps differ between walkers with different stride lengths, so steps since a turn
    from both partners' walks blur where the turn is.

**Decided**
- The table in `data/README.md` is the official walk count (finding 4).
- The board saves one CSV per walk, like HW7's recorder; the phone download is a backup
  (findings 2 and 5).
- Recording checklist: "if you mis-tap, tap Straight right away" (finding 6), Live mode
  and Auto-Lock Never (findings 1 and 2).
- `distance_m` added to `/api/state` and the CSV, next to `steps`; steps vs meters is
  compared on the first walks (finding 10).

**Page fixes** (`uno_q/assets/index.html`)
1. Start walk and Start navigating call `GET /api/reset` and only start once the board
   answers `{"ok": true}`. An answer to a request sent before the reset is thrown away.
   If the board refuses or doesn't answer, the walk doesn't start and the page says why.
2. The warning sits above both tabs (and stays at the top when scrolling), appears after
   1.5 s without an answer, clears as soon as the board answers, and greys out the
   instruction meanwhile. Each request now gives up after 1.5 s, because a dropped
   hotspot can make a request hang instead of failing.
3. Left/Right go back to Straight when the board's turn count goes up. Safety net: after
   10 steps with no turn counted, back to Straight anyway (otherwise a missed turn would
   label the rest of the walk Left). The cleanup rule from earlier stays as a backup.
4. Steps rounded down to whole steps; comment fixed; title "Nolop Navigator".

**Still open**
- **The page doesn't send rows to the board yet**, so the board can't save walks until it
  does (for example sending each row to the board as it is saved).
- A tap made *after* the board already counted the turn (a late tap) stays on until the
  10-step safety net. The cleanup's shift-earlier step has to handle late taps.
- Meters since the last turn: the board could send `distance_at_last_turn`, as it does
  `steps_at_last_turn`, so it doesn't have to be worked out from the rows afterwards.

**What the board app must provide**
1. The page itself: `assets/index.html` on port 7000 (`web_ui` brick).
2. `GET /api/state` → `{"steps", "distance_m", "turns_left", "turns_right",
   "steps_at_last_turn", "heading_deg", "on_stairs"}`. Decimals are fine for `steps` and
   `steps_at_last_turn` (the page rounds down). `steps_since_turn` and `turns` are worked
   out by the page and needn't be sent.
3. `GET /api/reset` → set every count to 0 (steps, distance, turns, steps at last turn,
   heading), then answer `{"ok": true}`, or `{"ok": false, "error": "..."}` if it can't.
4. Answer within 1.5 s, or the page treats the request as failed.
5. Save one CSV per walk with the columns in `data/README.md` (needs the page to send
   its rows, see Still open).
6. Later: run the trained policy, for example `GET /api/predict`, or hand the page the
   policy table.

## 2026-11-17: Rows sent to the board, and meters since the last turn

Checkpoint commit `e188a6c` before this work.

**Sending rows to the board** (`uno_q/assets/index.html`)
- Every saved row goes into an *outbox* on the phone, a waiting line, oldest first. Each
  tick sends the oldest waiting rows (up to 50) in one `POST /api/rows`. Only when the
  board answers `{"ok": true}` do they leave the line. If not, they stay and are tried
  again on the next tick. One send at a time, so the order is kept.
- Every message has a *ticket* (the page's session id + a number). If the board saved a
  batch but its "ok" got lost, the page sends it again and the board skips what it has.
- The outbox is also kept in the phone's storage, so rows waiting to be sent survive a
  page reload.
- Undo: a row still waiting is just dropped; a row the board may already have gets an
  "undo" message in the line, and the board removes it.
- The reset now says who is walking and the kind of walk
  (`/api/reset?walker=Raph&kind=demo`), and the board answers with its walk number,
  which goes on every row. So each row lands in the right walk's file, and the board's
  files and the phone's backup use the same numbers.
- The row count shows "all sent to the board" or "N waiting to send"; ending a walk with
  rows still waiting says to keep the page open.

**Meters since the last turn**
- `/api/state` gets `distance_at_last_turn` next to `steps_at_last_turn`. The CSV gets
  `distance_since_turn` next to `steps_since_turn` (the CSV has no `steps_at_last_turn`
  column, so the matching pair is the "since the turn" one). Both are worked out the same
  way, from the board's count at the moment it counted the turn, so steps vs meters is
  a fair comparison.

**Checked:** 33 checks against the fake board, all passing. They cover the board going
completely silent mid-walk (taps saved meanwhile wait on the phone, then arrive in order,
and the board's copy matches the phone's exactly), only the rows request failing, a lost
"ok" (no duplicates), undo before and after sending, rows waiting through a reload, two
walks going to two files, and mock mode sending nothing. Not checked: undo while that
row's batch is on its way (the code sends an undo in that case, but the test can't time
it), and anything on a real phone or board.

**Problems found while doing it**
- The backup download built its columns from the first row's fields, so the new private
  ticket would have become a junk column. It now writes exactly the CSV columns
  (checked).
- The first test run failed 11 checks: each tick sent waiting rows *before* saving that
  tick's new row, so the newest row always waited an extra quarter-second. The send now
  happens at the end of the tick.

**TURN_GIVE_UP_STEPS = 10 is a guess.** It is how many steps after a Left/Right tap the
page waits for the board to count the turn before going back to Straight. Check it on the
first real walks: how many steps after the tap does the board really count each turn
(rows where `turns` goes up)? It should be a few steps more than the slowest real turn,
but small enough that a missed turn doesn't label a long stretch as Left.

**What the board app must provide (replaces the earlier list)**
1. The page itself: `assets/index.html` on port 7000 (`web_ui` brick).
2. `GET /api/state` → `{"steps", "distance_m", "turns_left", "turns_right",
   "steps_at_last_turn", "distance_at_last_turn", "heading_deg", "on_stairs"}`. Decimals
   are fine; the page rounds.
3. `GET /api/reset?walker=<name>&kind=<demo|dagger>` → set every count to 0 (steps,
   distance, turns, both "at last turn" values, heading), start the next walk number,
   answer `{"ok": true, "walk": <number>}`, or `{"ok": false, "error": "..."}`.
4. `POST /api/rows` with `{"items": [...]}`, in order. Each item has `session` and `seq`,
   and either `row` (the CSV columns: append it to walk `row.walk`'s CSV) or `undo` (the
   `seq` of an earlier row from the same session: remove that row). Skip any item whose
   `seq` is not higher than the last one handled for that session. Answer `{"ok": true}`
   only once everything is saved to disk.
5. Answer every request within 1.5 s, or the page treats it as failed.
6. Later: run the trained policy, for example `GET /api/predict`, or hand the page the
   policy table.

## 2026-11-17: End of day 1 summary

**Decided**
- Layout as in the README; the phone page lives in `uno_q/assets/`.
- Start with Mohammed's HW7 step counter (runs on the board in plain numpy); Raph's CNN
  counter is the alternative being compared. Testing it on Raph's walking is the first
  checklist item. To confirm with Raph.
- Policy: a lookup table first (AnnaCode Table Cloner), a small net only if needed.
- The walk table in `data/README.md` is the official walk count (10 at most).
- The board saves one CSV per walk; the phone's download is the backup.
- Steps and meters are both saved (also since the last turn), to compare on the first
  walks.
- Phone hotspot rather than the board as its own Wi-Fi network.

**Built**
- Phone page fixes: reset the board before each walk (and only start once it confirms),
  a "can't reach the board" warning on both tabs with the instruction greyed out, turn
  labels that end when the board counts the turn (10-step safety net, a guess to check),
  whole steps, matching title.
- Row sending: a waiting line on the phone, tickets against duplicates, undo messages,
  walk numbers from the board, rows kept through a page reload. 33 checks against a fake
  board pass; not yet tried on a real phone or board.
- `uno_q/README.md`: the page ↔ board protocol in plain words, one example walk, and the
  build order (Step 0, then steps 1-9).
- Checklist: Live mode, Auto-Lock Never, tap Straight after a mis-tap, keep the page open
  until all sent, don't restart the hotspot mid-walk.

**Next (2026-11-18, with Raph)**
- Step 0, the hardware risk test: a sketch that records both sensors raw, one short walk
  with turns each, then check for dropouts and whether turns stand out in the waist gyro.
  If either fails, rethink before building the board app.
- Then the board app, in the build order in `uno_q/README.md`.
- The step-counter test on Raph's walking (checklist part 1) can be done with HW7's Step
  Recorder as it is.

## 2026-11-17: Turns from the ankle sensor (test on Raph's recording, no hardware)

**Test.** Mohammed ran `training/ankle_turn_check.py` on Raph's existing ankle recording
(`How many steps/data/walk_20261103_030045.csv` in Raph's repo: 61 counted steps, back and
forth over 2 m, 9 turnarounds, 100 Hz, about 6,000 rows). Method: "up" from the
accelerometer averaged over 1 s; the gyro's turning rate around "up", added up over time
into a heading; the gyro bias measured in the first 5 s, standing still, and subtracted.
Plot: [`media/ankle_turns_raph.png`](../media/ankle_turns_raph.png).

**What it showed**
- Turns stand out clearly at the ankle: 9 climbs, one per turnaround, and a flat heading
  while walking straight.
- No dropouts (no gap over 25 ms in about 6,000 rows). Short wire, so this says nothing
  about a long one.
- Each turnaround reads about 157° instead of 180° (all 9 together: 1409° instead of
  1620°), about 13% low. In any 2 s window each turnaround climbed 118-169°.
- Bias about 7.5°/s. Left in, the heading drifts about 450° in a minute, so the board must
  measure it while standing still at the start of every walk.
- Rerun and checked by Claude: the same numbers. Added check: on 9 of Mohammed's straight
  20 m HW7 walks (Test T21-T29, slow to fast, no turns), the ankle heading never changed
  by more than 14-20° within any 2 s (bias there taken as the walk's average, since a
  straight walk adds up to no turn). So ">60° within 2 s" sits between the walking wobble
  and the turnarounds with room on both sides.

**What it didn't prove**
- One walk by one person; only 180° turnarounds, all in the same direction; no 90° corners
  while walking; no left vs right; straight stretches of only 2 m.
- Why turns read 13% low isn't known: the averaged "up" lags behind the leg's tilt, or
  the walker didn't turn a full 180°. A loop that comes back to the start (known total:
  360°) separates the two.

**Decided**
- Step 0 becomes a one-sensor test: board and sensor on the ankle as in HW7 (short wire),
  loops with 90° left and right corners, the same heading plot. If it passes, the waist
  sensor and the long wire are dropped. The two-sensor test stays as the backup.
- Turn counting (build step 9) uses the ankle sensor and measures the bias while the
  walker stands still for 5 s right after Start. The waist sensor (step 8) only if Step 0
  fails.
- Checklist: stand still 5 s after pressing Start.
- `ankle_turn_check.py` now also reads HW7 recordings (`time` column), so Step 0 needs no
  new code: HW7's Step Recorder records the walk. Comments added; the calculations are
  unchanged (same output on Raph's walk).

**Added after the test: corner length.** A 90° corner taken while walking may take longer
than 2 s, so part of it would fall outside the 2 s window and it could read under 60°.
When checking the Step 0 loop plots, measure how long each corner's climb lasts. If
corners take longer than 2 s, **widen the turn window to 3 s instead of lowering the 60°
threshold**: a lower threshold moves toward the walking wobble, while a wider window
keeps clear of it (on HW7's straight walks the wobble stayed under 27° within 3 s,
against under 20° within 2 s).

## 2026-11-18: Step 0 on Raph's board (ankle sensor only)

Run from the terminal with HW7's Step Recorder app (`arduino-app-cli`, no App Lab) on
Raph's UNO Q; Raph's own app paused meanwhile, with his OK. Board and sensor on Raph's
right ankle as in HW7. Recordings in `data/step0/`, plots in `media/step0_*.png`.

**Tilt test:** the accelerometer reads ±1 g on each axis pointing up or down (others
within 0.16 g of 0). The gyro has a large steady offset: **gx about +34°/s when still**
(gy about 0, gz about -3), the same in all 7 still stretches. Raph's November recording
starts with gx = 35°/s, so probably the same sensor.

**LoopLeft** (Raph, 4 left corners, `Raph_Test_T01`) and **LoopRight** (Raph, 4 right
corners, `Raph_Test_T02`):

| | LoopLeft | LoopRight |
|---|---|---|
| Total heading change (per-axis bias) | +309° | -318° |
| Corners | +68, +78, +73, +80° | -89, -84, -79, -87° |
| How long each climb took | 1.0, 0.9, 1.6, 1.6 s | 1.6, 1.5, 1.4, 1.7 s |
| Biggest change within 2 s at a corner | 74-92° | 92-117° |
| Biggest change within 2 s walking straight | 17° | 23° |
| Rows of zeros / -1s, gaps over 25 ms | none | none |
| Steps: counted / live count | 28 / 26.4 ± 2.9 | 27 / 26.8 ± 3.8 |

So every corner clears 60° within 2 s, every climb is under 2 s (the window stays 2 s,
no need for 3 s), and the straights stay well under 60°. The HW7 step counter stayed
within its ± on this sensor despite the gx offset (two trials only).

**Finding: remove the gyro bias per axis, not as one number.** The script first measured
the bias as one number, the turning rate around "up" while standing still. But how much
of the gx offset shows up around "up" depends on how the shin is tilted, which differs
between standing and walking and changes every stride, so the subtracted number was a
little wrong the whole walk. Totals with one number: LoopLeft +350°, LoopRight -276°
(74° apart; LoopLeft's near-360° was luck). With the bias of gx, gy and gz each
subtracted before taking the part around "up": +309° and -318°, both about 12% short,
like Raph's November turnarounds (13%). `ankle_turn_check.py` now does this, and build
step 9 says so. (Raph's November walk barely changes: 1405° vs 1400°.) The steady ~12%
shortfall is not corrected: turns are only compared with 60°.

**Paired corners in LoopLeft.** Corners 1-2 and 3-4 came only 1-1.5 s apart. A simple
corner finder merged each pair into one ~170° turn. For the turn rule: a 3 s window would
also merge them, so widening it has a cost; and the pause before the next turn can count
must be shorter than about 1 s.

**Jump at the start of walking.** The heading rises +10° (LoopLeft) and +22° (LoopRight)
in the first steps after standing, positive both times whatever the turn direction:
probably the leg's angle changing from standing to walking. Under 60°, so it doesn't
count as a turn, but it adds to the totals.

**Possible left/right difference (needs more data).** Left corners read about 75° on
average, right corners about 85°. With the sensor on the right ankle it could be real
(a left turn swings the right foot around, a right turn pivots on it), but it is one
loop each, by one walker.

**Plots:** `ankle_turn_check.py`'s bias-removed plot now fits its scale to the data, with
a gray line every 90°, so corners are visible (before, the 180° lines forced it up to
1,800°). `media/ankle_turns_raph.png` is still the old plot.

**SpotTurns** (Raph, `Raph_Test_T03`: a left turn of about 180° on the spot, a ~3 s pause,
a right turn of about 180°; steps not counted, live count 2.8 ± 3.5 from the pivots):
- Turn 1 **+182°** (climb 2.3 s, 146° within 2 s), turn 2 **-181°** (climb 2.1 s, 179°
  within 2 s), total +1°. No rows of zeros or -1s, no gaps over 25 ms. Heading flat
  before, between and after.
- **Turns on the spot read the full angle; walking corners read about 12% short.** So
  the gyro's scale is fine and the shortfall comes from walking (likely the 1 s average
  of "up" while the shin swings). Not corrected, since turns are only compared with 60°.
- Spot turns took just over 2 s but still cleared 60° within 2 s easily, so the window
  stays 2 s. **Open for the turn rule:** with a pause under 1 s, a slow 180° turn could
  be counted twice; decide how a U-turn counts.
- The gx offset was 34.9°/s here (34.1 and 34.25 in the loops): it shifts a little
  between trials, so measuring it at the start of every walk is right.

**Mohammed's three trials** (`Mohammed_Test_T02`-`T04`; files renamed so both walkers fit:
`data/step0/Raph_*.csv` and `Mohammed_*.csv`, plots `media/step0_raph_*.png` and
`media/step0_mohammed_*.png`):

| | LoopLeft | LoopRight | SpotTurns |
|---|---|---|---|
| Total heading change | +280° | -356° | -10° (right -174°, left +164°) |
| Corners | +71, +73, +64, +83° | -89, -88, -95, -82° | -174°, +164° |
| How long each climb took | 1.6, 1.4, 1.3, 0.9 s | 1.4, 1.0, 1.0, 0.9 s | 2.2, 2.4 s |
| Biggest change within 2 s at a corner | 71-92° | 76-87° | 149°, 151° |
| Biggest change within 2 s walking straight | 18° | 14° | — |
| Rows of zeros / -1s, gaps over 25 ms | none | none | none |
| Steps: counted / live count | 28 / **18.5 ± 3.7** | 28 / **21.7 ± 3.7** | 0 / 4.6 ± 4.0 |

**Left vs right, both walkers:** left corners read lower for both: Mohammed 73° vs 88°
on average, Raph 75° vs 85°. For Mohammed at least part of it is a slow drift while
walking straight: his heading drifts *rightward* by about 3-5°/s on straight stretches
(LoopLeft: -22°, -22°; LoopRight: -4 to -17°), which pulls each left corner down and
pushes each right corner up by a few degrees, and takes 44° off his LoopLeft total.
Raph's straights drift the other way and less (0 to +2°/s). It can't be told apart from
a slightly curved path yet. Either way it is too slow to look like a turn (under 12°
within 2 s).

**Step 0 passes for both walkers.** No dropouts on any trial; every corner and spot turn
is a clear step in the right direction; every one changes more than 60° within 2 s (the
lowest: 71°, Mohammed's LoopLeft corner 2) and every climb is under 2 s except the slow
180° spot turns (2.1-2.4 s, which still clear 60° easily); straight walking stays under
23° within 2 s. **Decision: the waist sensor and the long wire are dropped; turns come
from the ankle sensor.** Thinnest margin: corners 71° vs the 60° rule, against 23° for
straights. A rule nearer the middle (about 45°) would leave more room both ways; to
decide when building step 9.

**New problem: the step counter undercounts Mohammed on this sensor.** Live counts were
18.5 and 21.7 for 28 counted steps (34% and 22% low, outside the ±), while Raph's two
loops were within the ± (26.4 and 26.8 for 28 and 27). The HW7 counter was trained on
Mohammed, so this isn't about the walker it learned from. Candidates: this sensor's gx
offset of about 34°/s (the counter's rotation-size features include it), a different
strap position, or the small loops' many corners (counters miss steps in turns). This
goes into the step-counter decision (checklist part 1).

## 2026-11-18: Experiment: does the sensor explain the undercount? (before/after swap)

**Question.** On Raph's sensor the HW7 step counter undercounted Mohammed's LoopLeft badly
(18.5 for 28 steps) but not Raph's (26.4 for 28). Raph's sensor has a gyro offset of about
34°/s on gx, and the HW7 counter was trained on Mohammed's own sensor. If the sensor is the
cause, swapping in Mohammed's sensor should fix Mohammed's count.

**What changed:** only the sensor (Mohammed's MPU-6050, the one the HW7 counter was trained
on, same wiring, 0x68). Same board, same app, same loop, same walkers, right ankle. The
sensor was swapped with the board on; the sketch's reconnect fix set it up again (log:
"no_answer" at 18:20:19, "reading again" at 18:20:57). Recordings in
`data/sensor_swap/`. Board trial T06 was walked by Raph but saved under Mohammed by
mistake: the copy `Raph_LoopLeft_MohammedSensor.csv` has its `person` column set to Raph;
the board's own files are unchanged.

**Mohammed's sensor, 10 s still on the table** (`MohammedSensor_Still.csv`, board T05):
gyro offset **gx -3.0, gy +2.2, gz -0.3°/s** (Raph's: gx +34.9, gy -0.3, gz -2.9),
noise 0.1°/s per axis. No dropouts.

**Step counts, LoopLeft, 28 counted steps each:**

| Walker | Raph's sensor (before) | Mohammed's sensor (after) |
|---|---|---|
| Mohammed | 18.5 ± 3.7 (-34%) | **22.0 ± 3.7** (-21%), board T07 |
| Raph | 26.4 ± 2.9 (-6%, within ±) | **32.1 ± 3.0** (+15%, outside ±), board T06 |

**What it showed**
- The swap raised *both* walkers' counts, by 3.5 and 5.7 steps: this sensor makes the
  counter count more, for everyone. It didn't fix Mohammed specifically.
- **On both sensors, Mohammed's walk counts about 8-10 steps fewer than Raph's** for the
  same 28 steps (18.5 vs 26.4; 22.0 vs 32.1). So the main cause is how Mohammed walks
  these small loops, not the sensor. The HW7 counter was trained on 20 m straight walks;
  tight loops with four corners may look different in his gait.
- Neither sensor gets both walkers right: Raph's sensor fits Raph, Mohammed's sensor
  still undercounts Mohammed and now overcounts Raph.
- Turns don't care about the sensor: LoopLeft totals +319° for Raph (+309° on his sensor)
  and +273° for Mohammed (+280° on Raph's sensor). Mohammed's rightward drift on the
  straights showed up again on the new sensor, so it follows the walker (gait or a
  slightly curved path), not the sensor.

**What it didn't prove:** one trial per walker and sensor, so the normal spread between
repeats of the same walk is unknown (a few steps would be enough to blur this). The strap
position also changed with every swap.

**For the step-counter decision (checklist part 1):** the HW7 counter as it is can't be
trusted on loops with corners: 22-34% off for Mohammed on either sensor. Options: test it
on straight walks with each sensor (what it was trained for), retrain it with both
walkers' walks including corners, or compare Raph's CNN counter on the same recordings.

## 2026-11-18: Raph's CNN counter on today's recordings (offline, on the laptop)

`training/compare_raph_cnn.py` runs Raph's counter (his `step_net.py` and
`models/step_net.pt` from his repo, unchanged) over every recording from Step 0 and the
sensor swap. Nothing on the board changed. His model is loaded with `weights_only=True`
(his own loader allows the model file to run code). Check first: on his own November walk
it counts 52 of 61 steps (his report: 50).

**As recorded, it counts 0 steps on every walk.** The reason is how the sensor sits on the
leg: in his recordings gravity is on the sensor's y axis and the leg swings on y and z;
HW7's strap puts gravity on x and the swing on x and z. His training tilted the data up to
25° and flipped signs but never swapped axes, so his nets have never seen a swing on our
axes. With our axes renamed to his layout (his x = our y, his y = our x, his z = -our z, a
plain rotation; the mirror-image version without the z flip does much worse):

| Recording | Counted | HW7 counter (live) | Raph's CNN |
|---|---|---|---|
| Raph LoopLeft (Raph's sensor) | 28 | 26.4 | **28** |
| Raph LoopRight (Raph's sensor) | 27 | 26.8 | **28** |
| Raph SpotTurns | 0 | 2.8 | **2** |
| Mohammed LoopLeft (Raph's sensor) | 28 | 18.5 | **26** |
| Mohammed LoopRight (Raph's sensor) | 28 | 21.7 | **28** |
| Mohammed SpotTurns | 0 | 4.6 | **0** |
| Mohammed's sensor, still on the table | 0 | 0.2 | **0** |
| Mohammed LoopLeft (Mohammed's sensor) | 28 | 22.0 | **28** |
| Raph LoopLeft (Mohammed's sensor) | 28 | 32.1 | **28** |

**What it shows:** once the axes match, Raph's counter is within 2 steps on every
recording: both walkers, both sensors, loops with four corners. The HW7 counter was off by
up to 10 steps and depended on walker and sensor. Raph's counter finds each stride of the
strapped leg directly, which seems to hold up in corners and for both gaits, where HW7's
counter (a rate estimated from 2 s clips, trained on straight walks) doesn't. It only
counts whole strides, so counts come in steps of 2. Limits: one recording per walker,
sensor and loop; the axis renaming was chosen from these recordings' orientation (where
gravity and the swing are), not from the counts.

## 2026-11-18: Step-counter decision so far

**Decision:** no more dedicated step-counter tests (no straight walks). The counter is
judged from the real route demos: both walkers walk the same route, and their step totals
are compared.

**Why that is enough for now:**
- **The turn count does most of the work in the policy.** Which leg of the route the
  walker is on comes from the number of left and right turns, and Step 0 showed the ankle
  gyro counts every corner clearly for both walkers.
- **Steps since the last turn only time the warnings:** when to say "turn left soon" on a
  straight stretch. An error of a few steps there shifts a warning a little; it doesn't
  send the walker the wrong way.
- **The route demos will show how far apart our counts are.** Both walkers on the same
  route, each stretch between turns the same length: if their steps since the last turn
  disagree a lot, the policy will blur where the warnings go, and that shows up in the
  labels and in training.

**What today's comparison adds:** Raph's CNN counter, with the axes renamed, matched the
counted steps on every recording, while the HW7 counter undercounted Mohammed by up to a
third. It is the stronger candidate for the route demos. To use it live it needs: its
nets in plain numpy on the board (as HW7's counter is), and the axis renaming built in.
To decide before the first route demo.

## 2026-11-18: Decision: Raph's CNN counter for the route demos

**Decided (Mohammed and Raph):** the route demos use Raph's CNN step counter, not the HW7
counter.

**Why:**
- On every recording from today (both walkers, both sensors, loops with four corners and
  spot turns) it was within 2 steps of the counted steps, once our axes are renamed to his
  layout. The HW7 counter was off by up to 10 of 28 steps and depended on walker and
  sensor (it undercounted Mohammed by 21-34% on either sensor).
- It finds each swing of the strapped leg directly, which held up in corners; the HW7
  counter estimates a rate from 2 s clips and was trained on straight walks only.
- Steps since the last turn time the warnings, and both walkers' demos go into one
  policy, so a counter that agrees across walkers matters more than one that suits one
  person.

**What it needs before the first route demo:** its five nets in plain numpy on the board
(the board has no PyTorch; HW7's counter already runs this way), the axis renaming built
in, and a check that the numpy version gives the same output as his PyTorch version.

## 2026-11-18: Distance decision, and Raph's counter ported to numpy

**Distance:** `distance_m` stays in `/api/state` as steps × 0.41 m (Raph's fitted 0.823 m per
stride), so nothing on the page or in the protocol changes. **The steps-vs-meters
comparison is dropped:** with this counter, meters are just steps times a constant, so they
add no information; and a stranger following the guide wouldn't have a stride-length
setting of their own anyway.

**Steps arrive late and in twos:** a stride is counted about 0.6-0.85 s after it happens
(once it is 0.6 s old, checked every 0.25 s), and the count goes up by 2. So "steps since
the last turn" also jumps by 2, a little late. Fine for now; to remember when timing the
warnings before a turn.

**Speed on the UNO Q:** a numpy forward pass with StepNet's exact layer sizes (random
weights), 5 nets on one 4 s window: **35 ms median** (36.6 ms slowest) inside the app's
container on the board, while Step Recorder ran. One window every 250 ms = about 14% of one
of the 4 cores. Fast enough.

**Export** (`training/export_raph_cnn.py`): Raph's `models/step_net.pt` (his commit
`713da130607d`, loaded with `weights_only=True`) -> `uno_q/python/raph_step_model.npz`,
weights unchanged, plus his counting settings, the axis swap and the stride length.
**16,201 trainable weights per net**, matching Raph's Notion page, plus 288 batch-norm
running averages. 329 KB for all five.

**Port** (`uno_q/python/stride_counter.py`, numpy only): the same layers (conv 8->24 with
stride 2, batch norm, ReLU; five dilated blocks 1-16 with batch norm, ReLU and the input
added back; 1x1 output; linear stretch to 400; sigmoid), his input preparation (including
(|acc| - 1) / 2 and |gyro - median| / 300), his counting rule line for line (threshold 0.5,
0.4 s apart, counted at 0.6 s old, 1 s of context, steps from the average's peaks, each
net's own count for the ±), scipy's find_peaks rewritten in numpy (flat tops counted once,
at the middle), and a live counter with the same controls as HW7's.

**Check** (`training/check_numpy_port.py`, PyTorch vs numpy on the same windows, all nine
recordings from today plus Raph's November walk): largest score difference anywhere
**7.5 × 10⁻⁷** (tolerance 10⁻⁵); peaks identical to scipy's in every window; the same
strides at the same samples, the same per-net counts and the same steps on every recording
(26/28/0/28/28/2/0/28/28 and 52 on his walk); the live counter, fed one sample at a time,
gives the same steps. Not yet run on the board itself (build step 4).

**Port review:** Mohammed and Raph read `prep`, `find_peaks` and `StrideCount.update` in
`stride_counter.py` against Raph's `step_net.py`: it looks right. Together with the
side-by-side check above.

**Raph's sensor back on** (swapped with the board on: "no_answer" at 18:43:04, "reading
again" at 18:44:05). Still test on the table (`data/sensor_swap/RaphSensor_Still.csv`,
board `Raph_Test_T04`): gyro offset **gx +35.1, gy -0.6, gz -2.5°/s**, noise 0.1°/s, no
dropouts. gx of about +35°/s confirms it is Raph's sensor (Mohammed's: -3.0).

## 2026-11-18: Board app step 1 on the board; walking days on the board's own network

**Build step 1 runs on Raph's board** (from the terminal, `arduino-app-cli`): the page is
served on port 7000, byte for byte the repo's page; Mock mode works (steps, since turn,
turns, Start/End walk, Download CSV). Step Recorder stopped meanwhile; all of today's board
recordings and the board's trial logs were copied to `data/` first.

**Decided (Mohammed and Raph; Chris confirmed that running our own Wi-Fi network on campus
is OK):** Mohammed's phone can't use Tufts_Robot and we don't use a phone hotspot, so on
walking days the board makes its own Wi-Fi network, **NolopNav**, with the page always at
http://10.42.0.1:7000. Build step 2 (the address on the LED matrix) is skipped.
- NolopNav starts by itself on walking days (so a power-bank swap mid-walk brings it back),
  and the board goes back to Tufts_Robot each evening.
- Mohammed types the password himself; it stays in the board's network settings only, not
  in the repo or any notes.
- Nolop Navigator is the default app on walking days, switched back with the network.
- Network changes go over the USB-C cable (adb), tested first. Checked today: the Wi-Fi
  chip supports hotspot mode, the `arduino` user may change network settings without the
  admin password, adb is on the laptop (App Lab's), but the board showed **no USB data link**
  yet (not plugged in, or a charge-only cable). `arduino-app-cli` has no command to clear a
  default app, so the evening step sets one Raph chooses.
- Commands and the switch-back steps: `uno_q/README.md`, "Walking days". Not switched yet:
  the build continues on Tufts_Robot until the app is ready for real walks.

**Build step 3 runs on the board** (19:09): HW7's sketch (unchanged, new header comment) and
`python/sensor.py`, which collects the readings 10 times a second, checks each one (all
zeros = lost power, raw -1 = no answer), counts lost readings from the running numbers and
logs a summary every 10 s. Raph's sensor flat on the table: **999 readings in 10.1 s, 0
lost, 0 bad**, latest gx +34.9 to +35.1°/s (his sensor's offset), az -1.05 g. (The first
summary showed 1,391: the readings queued while the app started, collected in one go.)
Change from HW7: a batch that arrives cut short is still dropped, but the last running
number is kept, so the next batch shows how many readings were lost; each lost reading
becomes a "not real" placeholder, so the step counter's 4 s window stays 4 s (step 4).

**Evening default app:** Raph's How Many Steps (`/home/arduino/ArduinoApps/Steps-UnoQ`), the
app that was running when we started on his board, so each evening the board goes back to
how Raph had it (Raph agreed). **USB test, second try (19:20):** still no link: adb listed no
device and the laptop's USB list showed no board at all, with the cable that worked with App
Lab this morning. The laptop had also left Tufts_Robot (address 10.243.41.251), so the board
couldn't be reached over Wi-Fi either. To retry.

**USB test passed (19:16)**, once the board was plugged in again (it restarted on plugging
in): `adb devices` lists it, `adb shell` reaches the board named Raph as user `arduino`, and
over USB that user may change network settings. So NolopNav can be switched over the cable.

**Build step 4 runs on the board** (19:18): `main.py` feeds every reading (placeholders for
lost ones too) to `LiveStrideCounter` and logs the steps each time they change, plus a
summary every 10 s with how long the 5 nets took. First tested on the laptop with stand-ins
for the board's libraries, replaying Raph's LoopLeft in batches (one cut short): 28 steps,
the same as the checked port, and 10 lost readings filled in. On the board, standing still:
1,015 readings in 10.2 s, 0 lost, **0 steps**; the nets ran 41 times in 10 s, **median
49 ms, slowest 52 ms** (91 ms only for the first run), against a budget of one run every
250 ms: about 20% of one core. (The speed test's 35 ms left out the input preparation and
peak finding.)

**Problem after the board restarted:** the sketch didn't answer Python at all
(`get_batch` timed out every 10 s), and the router never saw the sketch register its
functions; it logged bursts of "invalid packet, expected array" instead. Starting the app
again and recreating its container didn't help; **restarting the app, which flashes the
sketch again, did**. Cause unknown (possibly the microcontroller starts before Linux's
router is ready after a power-up, so its first messages are lost). **To test before the
first walk:** with Nolop Navigator as the default app, power-cycle the board (as a power-bank
swap would) and check readings flow; if they don't, the app could restart itself when no
readings arrive at all.

Also after the unexpected power-off: the app container's log file had a stretch of null
bytes (the log was being written when the power went), so `app logs` stopped there. Fixed
by deleting Nolop Navigator's container (`docker rm nolop-navigator-main-1`; the CLI built a
fresh one on the next start). Only the old log lines were affected.

**Known limit of the live counter:** while a 4 s window holds a "not real" reading (a lost
or bad one), the nets don't run, so a cut-short batch while walking loses the strides of
about 1.6 s around it (2-4 steps). Cut-short batches came about 6 times an hour today.
