# Recording checklist

## Once, before the first trial

- [ ] Away from home: turn on Phone 2's Personal Hotspot and keep that settings screen open.
- [ ] Board strapped to the right lower leg, near the ankle, then plug in the power bank.
- [ ] Wait for the LED matrix to scroll the address (`172.20.10.x:7000` on the hotspot).
- [ ] Phone 2: open `http://<that address>`. The page title is **Step Recorder**, and the
      matrix switches to a dot.
- [ ] phyphox: **+** → simple experiment **Ankle trial**: Accelerometer + Gyroscope, 100 Hz.
- [ ] phyphox: a second one, **Ankle trial GPS**: the same plus Location (Outdoor only).
- [ ] Course marked: 20 m, start and finish lines.

## Every trial

1. **Step Recorder page:** pick the name and activity. Note the **Next file** name.
2. **phyphox:** clear the old data (trash icon), open **Ankle trial** (or **Ankle trial GPS**
   for Outdoor), press ▶.
3. Phone in pocket. **Step Recorder: Start.** LED shows **R**.
4. Stand still 2 s. **Stomp once, hard**, with the ankle leg. Stand still 1 s.
5. Do the activity. Count every step, both feet. (LegSwing: stomp first, then sit.)
6. Stand still 2 s at the end.
7. **Step Recorder: Stop.** LED shows **?**.
8. **phyphox: ⏸.**
9. **Step Recorder:** type in **Steps** and **Distance** (20 m, or 0 for Stand / Fidget /
   LegSwing), then **Save**. LED back to a dot.
   Messed up? **Discard** instead, and redo the trial.
10. **phyphox: ⋮ → Export Data → CSV (Comma, decimal point)**. Save the zip as the trial's
    name, shown under the Save button (e.g. `Mohammed_Walk_normal_T03.zip`).

Wrong count saved? **Delete last trial** on the page, then redo it.

## Outdoor walk

- Use **Ankle trial GPS** and let it find a GPS fix before the stomp.
- Note the phone's step count (Health / Fitness) just before Start and just after Stop.
- Steps = the difference. Distance = the phone's distance (or the GPS track).

## After the session

- [ ] Laptop: `python "Mohammed's Projects/How Many Steps/data/sync_from_board.py"`
- [ ] Copy the phyphox zips into `data/phone_raw/`.
- [ ] Run the sync again: it lists any trial missing a count or a phone zip.
