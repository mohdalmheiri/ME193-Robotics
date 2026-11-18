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
