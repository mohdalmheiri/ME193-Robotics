# Recording checklist

No helper: **Phone 1** stays in the pocket and only runs phyphox. **Phone 2** stays in
the hand: it runs the hotspot and the Step Recorder page, and films the feet for a few
trials.

## Once, before the first trial

- [ ] **Phone 1:** Settings → Display & Brightness → **Auto-Lock → Never** (phyphox stops
      recording when the screen locks).
- [ ] **Phone 1:** phyphox has the simple experiments **Steps - Motion** (Accelerometer +
      Gyroscope, 100 Hz) and **Steps - GPS** (the same plus Location, Outdoor only). Keep
      "GPS" in that title: `.gitignore` uses it to keep GPS zips off GitHub.
- [ ] **Phone 1:** always the same phone, the same pocket and the same direction (e.g.
      right front pocket, screen facing the leg, top up). Don't change it between trials.
- [ ] **Phone 2:** turn on Personal Hotspot and keep that settings screen open.
- [ ] Board strapped to the right lower leg, near the ankle, then plug in the power bank.
- [ ] Wait for the LED matrix to scroll the address (`172.20.10.x:7000`).
- [ ] **Phone 2:** open `http://<that address>` in Safari. Title **Step Recorder**, matrix
      shows the live step count.
- [ ] Course: 20 m, start and finish lines marked.

## Every trial (training trials: the paces, Stand, Fidget, LegSwing)

1. **Phone 2:** pick the name and activity on the Step Recorder page. Note the
   **Next file** name.
2. **Phone 1:** phyphox **Steps - Motion**, check it's empty, press ▶. Into the pocket.
3. **Phone 2: Start.** The LED's top row lights up across (recording).
4. Stand at the start line, still for 2 s. **Stomp once, hard**, with the ankle leg. Still 1 s.
5. Walk (or run) **one way** to the finish line, 20 m. Count your steps **silently**: every
   foot that lands, both feet, from the first step to the last. The stomp isn't a step.
   (Stand / Fidget: stay in place. LegSwing: stomp, then sit and swing.)
6. Stand still 2 s at the finish.
7. **Phone 2: Stop.** LED shows **?**.
8. **Phone 1:** take it out, phyphox **⏸**.
9. **Phone 2:** type in **Steps** and **Distance** (20, or 0 for Stand / Fidget / LegSwing),
   then **Save**. LED back to the step count. Messed up? **Discard** and redo the trial.
10. **Phone 1: export first:** **⋮ → Export Data → CSV (Comma, decimal point)**, save to
    Files. Keep phyphox's own name; the laptop matches it by time.
11. **Phone 1: then clear** the data (trash icon), ready for the next trial.

Wrong count saved? **Delete last trial** on the page, then redo it.

## Test walks (checking the live count)

The finished model only uses the ankle, so Test walks need no stomp, no phyphox and no
measured course. Walk anywhere.

1. **Phone 2:** pick **Test** on the Step Recorder page, then **Reset count** (so the Live
   count shows just this walk).
2. **Start.** Walk, counting your steps **silently** (every foot that lands, both feet).
3. **Stop.**
4. Type in **Steps**, and the **Distance** only if you really know it; otherwise **0**
   (0 = unknown; the box starts empty for Test). **Save.** The board stores its live count for the walk in
   `live_counts.csv`, and the saved-trials table shows it.

A wrong number saved anyway? Add a row to `data/trial_corrections.csv` rather than
editing `trials.csv` (see `data/README.md`).

## Filmed trials (about 5)

One each of Walk_slow, Walk_normal, Walk_fast and Run, to check the counts later.
Same steps as above, with Phone 2 also filming:

- Before step 3: Control Center → **Screen Recording** on, while the page shows **Next
  file** (so the video names its trial).
- After **Start**: open **Camera** and point it at your feet for the walk.
- After the finish: back to Safari, **Stop**, enter the count, **Save**, then stop the screen
  recording. The video holds the file name, the feet and the count you typed.

## Outdoor walk

- **Phone 1:** use **Steps - GPS** and let it find a GPS fix before the stomp.
- Note Phone 1's step count (Health) just before Start and just after Stop.
- Steps = the difference. Distance = Phone 1's distance (or the GPS track).

## After the session

- [ ] **Phone 1: Auto-Lock back on** (Settings → Display & Brightness → Auto-Lock).
- [ ] **Phone 2:** turn off Personal Hotspot.
- [ ] Laptop: `python "Mohammed's Projects/How Many Steps/data/sync_from_board.py"`
      (the board must be back on home Wi-Fi).
- [ ] Copy the phyphox zips, as named, into `data/phone_raw/original_zips/`.
- [ ] `python check_recordings.py` in `data/`: for each new zip it says which trial folder to
      unzip it into (e.g. `phone_raw/Mohammed_Walk_normal_T03/`). Unzip them there.
- [ ] Run `check_recordings.py` again: every trial should say OK. It also saves the real
      lengths and makes the plots. Add any damaged trial to `excluded_trials.csv` with the
      reason, and any wrong count or distance to `trial_corrections.csv` (don't edit
      `trials.csv`); the end of the printout shows how many good trials each activity has.
- [ ] Run the sync again: it lists any trial still missing a count or a phone folder.
- [ ] Watch the filmed trials and compare with `trials.csv`.
