# Recording checklist

No helper: **Phone 1** stays in the pocket and only runs phyphox. **Phone 2** stays in
the hand: it runs the hotspot and the Step Recorder page, and films the feet for a few
trials.

## Once, before the first trial

- [ ] **Phone 1:** Settings → Display & Brightness → **Auto-Lock → Never** (phyphox stops
      recording when the screen locks).
- [ ] **Phone 1:** phyphox has the simple experiments **Ankle trial** (Accelerometer +
      Gyroscope, 100 Hz) and **Ankle trial GPS** (the same plus Location, Outdoor only).
- [ ] **Phone 1:** always the same phone, the same pocket and the same direction (e.g.
      right front pocket, screen facing the leg, top up). Don't change it between trials.
- [ ] **Phone 2:** turn on Personal Hotspot and keep that settings screen open.
- [ ] Board strapped to the right lower leg, near the ankle, then plug in the power bank.
- [ ] Wait for the LED matrix to scroll the address (`172.20.10.x:7000`).
- [ ] **Phone 2:** open `http://<that address>` in Safari. Title **Step Recorder**, matrix
      shows a dot.
- [ ] Course: 20 m, start and finish lines marked.

## Every trial

1. **Phone 2:** pick the name and activity on the Step Recorder page. Note the
   **Next file** name.
2. **Phone 1:** phyphox **Ankle trial**, check it's empty, press ▶. Into the pocket.
3. **Phone 2: Start.** LED shows **R**.
4. Stand at the start line, still for 2 s. **Stomp once, hard**, with the ankle leg. Still 1 s.
5. Walk (or run) **one way** to the finish line, 20 m. Count your steps **silently**: every
   foot that lands, both feet, from the first step to the last. The stomp isn't a step.
   (Stand / Fidget: stay in place. LegSwing: stomp, then sit and swing.)
6. Stand still 2 s at the finish.
7. **Phone 2: Stop.** LED shows **?**.
8. **Phone 1:** take it out, phyphox **⏸**.
9. **Phone 2:** type in **Steps** and **Distance** (20, or 0 for Stand / Fidget / LegSwing),
   then **Save**. LED back to a dot. Messed up? **Discard** and redo the trial.
10. **Phone 1: export first:** **⋮ → Export Data → CSV (Comma, decimal point)**, save to
    Files as the name under the Save button (e.g. `Mohammed_Walk_normal_T03.zip`).
11. **Phone 1: then clear** the data (trash icon), ready for the next trial.

Wrong count saved? **Delete last trial** on the page, then redo it.

## Filmed trials (about 5)

One each of Walk_slow, Walk_normal, Walk_fast, Run and Test, to check the counts later.
Same steps as above, with Phone 2 also filming:

- Before step 3: Control Center → **Screen Recording** on, while the page shows **Next
  file** (so the video names its trial).
- After **Start**: open **Camera** and point it at your feet for the walk.
- After the finish: back to Safari, **Stop**, enter the count, **Save**, then stop the screen
  recording. The video holds the file name, the feet and the count you typed.

## Outdoor walk

- **Phone 1:** use **Ankle trial GPS** and let it find a GPS fix before the stomp.
- Note Phone 1's step count (Health) just before Start and just after Stop.
- Steps = the difference. Distance = Phone 1's distance (or the GPS track).

## After the session

- [ ] **Phone 1: Auto-Lock back on** (Settings → Display & Brightness → Auto-Lock).
- [ ] **Phone 2:** turn off Personal Hotspot.
- [ ] Laptop: `python "Mohammed's Projects/How Many Steps/data/sync_from_board.py"`
      (the board must be back on home Wi-Fi).
- [ ] Copy the phyphox zips into `data/phone_raw/`.
- [ ] Run the sync again: it lists any trial missing a count or a phone zip.
- [ ] Watch the filmed trials and compare with `trials.csv`.
