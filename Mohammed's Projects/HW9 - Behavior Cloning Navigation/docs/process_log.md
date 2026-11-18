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
