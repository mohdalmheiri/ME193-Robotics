# Recording checklist

## 1. First: test the step counter on Raph's walking

The HW7 counter was trained only on Mohammed's walking, and only tested on straight
20 m walks. Before any route walk, check it on Raph, and on walks with turns. These are
short test walks, not full route walks, so they don't use up the 10-walk budget.

Use HW7's **Step Recorder** app as it is (its **Test** activity): it already counts live
on the board and saves each test walk's live count next to the real one.

- [ ] Deploy Step Recorder (`python3 tools/deploy.py step-recorder`) and open the page on
      the phone (address scrolls on the LED matrix).
- [ ] Strap the board to **Raph's** right lower leg, near the ankle, the way HW7 was worn.
- [ ] Name **Raph**, activity **Test**, **Reset count**.
- [ ] 3 straight walks each at slow, normal and fast pace. Raph counts every step silently
      (both feet). Stand still 2 s before **Stop**, type in the count, **Save**.
- [ ] 3 walks with turns (for example a walk around a corner and back), counted the
      same way, by **both** Raph and Mohammed. Note the number of turns in each.
- [ ] Sync to the laptop (HW7's `data/sync_from_board.py`) and compare live count vs real
      count per walk. Write the results and the decision in `docs/process_log.md`.
- [ ] **Decide:** keep the HW7 counter, retrain it with Raph's walks added, or switch to
      Raph's counter. Confirm with Raph.

## 2. Once, before the first route walk

- [ ] Route fixed: start point, every turn, any stairs, the Nolop door. Written in
      `docs/process_log.md`.
- [ ] Both sensors read on a real walk (the waist sensor's long wire especially).
- [ ] Phone hotspot on, board joined, page opens, **Data: Live (UNO Q)** selected. Mock
      mode never talks to the board, so a page that works in Mock can still fail on the
      board: test one short Live walk first.
- [ ] Phone: Settings → Display & Brightness → **Auto-Lock → Never**. A locked iPhone
      stops the page asking the board for numbers, so steps taken while it's locked get
      no rows.
- [ ] Plan how the 10 walks are split, for example demos by both partners first, then
      correction walks. Keep a few for corrections.

## 3. Every route walk

1. Board on, ankle sensor on the right lower leg, waist sensor on the belt (same spot
   every time).
2. Stand still at the start for 2 s, so the gyro's resting offset can be measured.
3. **Record demo** tab (demo) or **Navigate + correct** with "Save my corrections" ticked
   (DAgger). Press **Start**, and wait until the page says the walk has started (the
   board confirms its counts are back at 0). Tap the action as you start doing it.
   - **If you mis-tap, tap Straight right away** (or the right action). A wrong label
     stays on for every step until the next tap, and Undo only removes the tap itself.
   - Left and Right go back to Straight by themselves once the board counts the turn.
     Stairs and Arrived stay on until your next tap.
   - A red **Can't reach the board** warning means the numbers are frozen: stop and
     check the hotspot and the power bank.
4. At Nolop, press **Arrived**, then stop recording. Keep the page open until the row
   count says **all sent to the board**.
5. Fill in this walk's row in the budget table in `data/README.md`, even if the walk
   went wrong.
