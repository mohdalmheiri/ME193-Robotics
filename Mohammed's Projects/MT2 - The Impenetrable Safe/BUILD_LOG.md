# Build log: The Impenetrable Safe (MT2)

A short running record of what was tried, what failed and what fixed it.

- **2026-11-07: folder set up.** Created this folder layout. The motor test
  sketch, DXF, STL and CAD scripts were supposed to be copied from
  Downloads, but they were not there (or anywhere else on the laptop), so
  those folders are still empty.
- **2026-11-07: CAD left out of the repo.** Decided not to keep CAD
  files here, so the `cad/` folder was removed.
- **2026-11-07: PWM pins checked.** Read the UNO Q's pin table on the
  board itself (the Zephyr core 1.1.0 variant file). D9 and D10 both
  support PWM (`analogWrite`), at 500 Hz.
- **2026-11-07: possible power problem noted.** The motor is powered from
  the UNO Q's 5V pin, which comes from the laptop's USB. A TT motor can draw
  a lot of current when it starts or gets stuck, which could make the board
  reset. If that happens, power VB+/VB- from a separate battery pack
  instead (keep the GND link to the UNO Q).
- **2026-11-07: motor test deployed.** Copied `latch_motor_test.ino`
  unchanged into an App Lab app (renamed to `sketch/sketch.ino`, because
  the compiler only accepts a main file named after its folder). Deployed
  over USB with `deploy.py`: it compiled, flashed and started with no
  errors. The board's Linux side kept running through the first motor
  swings (no restart).
- **2026-11-07: motor test works.** Watched the motor: it alternates
  direction about every 2 s, exactly as the sketch intends (300 ms swing,
  2 s pause, 300 ms swing back, 2 s pause). That also shows the
  microcontroller is not resetting: a reset restarts the sketch, which
  always swings the same way first, so the motor would keep going one way.
  USB power is enough for the motor so far. Still to check: how far the
  attached latch arm turns in 300 ms at speed 150.
- **2026-11-07: warm-up built.** Single neuron (hand-written gradients),
  the 5-iteration Excel workbook and the two-neuron PyTorch fit. The
  Excel formulas give exactly the same m, b, loss and gradients as
  `single_neuron.py` for iterations 0 to 5 (checked by evaluating every
  formula, at learning rate 0.5 and again at 2.0). Learning rate: 0.05 and
  0.2 barely moved in 5 steps, 0.5 and 1.0 dropped the loss every step,
  2 and 4 overshot (the loss went up). Results: one neuron ends at
  loss 0.0950; two neurons reach 0.0004, about the size of the noise.
- **2026-11-07: two-neuron starts can get stuck.** Only 6 of 10 random
  starting points found the V; in the other 4, one or both hidden neurons
  ended up switched off for every point ("dead") and stopped learning.
  `two_neurons.py` now tries 10 starts and keeps the best. A learning rate
  of 0.5 made this happen more often, so it uses 0.1 for 5000 epochs.
- **2026-11-07: Excel could not be scripted.** Tried to have Excel itself
  recalculate the workbook through AppleScript to check its numbers; it
  timed out on the sandbox's file permission, then reported saves that
  never wrote a file. The check was done instead with the `formulas`
  Python package, which evaluates each cell's formula the way Excel does.
- **2026-11-07: data-collection tool written.** `capture.py` and
  `hand_crop.py`, tested on a made-up desk picture (red square found,
  crop and resize, file names, counts, the window drawing). Not yet tried
  with the real webcam: it was not plugged in (macOS listed only the
  built-in FaceTime camera and two iPhones).
- **2026-11-07: latch arm swung too far.** With the arm mounted in the box,
  300 ms at speed 150 turned it about 135°. Changed the sketch:
  - LOCK runs 200 ms (wall → straight out, about 90°).
  - UNLOCK runs 250 ms back, slightly longer than needed, so the arm
    presses gently on the wall and always stops in the same spot (the
    wall is its "home", because the motor can't sense where it is).
  - `LOCK_MS` and `UNLOCK_MS` can be tuned separately.

  The sketch didn't say which pin turns the arm toward the wall, so a
  direction check was deployed over Wi-Fi (`DIRECTION_CHECK = true`,
  guessing M1A). The first version made one 250 ms swing toward the wall
  5 s after starting. Twice, nobody saw anything move. That fits the arm
  already resting on the wall (pushing into it shows no movement), but
  "the motor didn't run" would look the same.

  The check was changed to wait 15 s, then do one LOCK and one UNLOCK. The
  arm swung out from the wall, then back to it. So **M1A = toward the
  wall** (`WALL_IS_M1A = true`). The normal lock/unlock loop was then
  deployed.
- **2026-11-07: latch timings tuned.** At LOCK 200 ms / UNLOCK 250 ms, the
  arm stopped a bit short of 90° and hit the wall hard on the way back
  (50 ms of extra push was too much). Changed to LOCK 220 ms / UNLOCK 235 ms,
  only 15 ms extra, and deployed.
- **2026-11-07: soft landing on the wall.** At 220 ms the arm went a bit
  past 90°, and it still hit the wall hard even with only 15 ms of extra
  push. So the problem was speed, not time: the arm reached the wall
  going full speed. Changes, then deployed:
  - LOCK is now 210 ms (between the 200 ms that was short and the
    220 ms that was over).
  - UNLOCK is now two parts: 160 ms at speed 150, then 100 ms at speed
    100, so the arm slows down before reaching the wall.
- **2026-11-07: slower return.** At 210 ms the arm stopped short of 90°,
  and it still hit the wall: 160 ms at full speed probably carried it
  nearly all the way back before the slow part began. Changes, then
  deployed:
  - LOCK is now 215 ms.
  - UNLOCK is now 110 ms at speed 150 (about half the way), then 180 ms
    at speed 90.
- **2026-11-07: drift seen, slow part lengthened.** The arm no longer hit
  the wall, but it stopped with a gap that grew a little every cycle, and
  LOCK went past 90°. This is the drift the wall was supposed to prevent:
  each return fell short, so the next LOCK started further out.

  Speed 90 moves the arm more slowly than estimated. The slow part was
  raised from 180 ms to 350 ms so the arm always reaches the wall. Extra
  time there is harmless: at that low speed the arm just leans on the
  wall. LOCK is left at 215 ms until the return reliably reaches the wall,
  because the earlier overshoot came from starting out of place.
- **2026-11-07: drift fixed, softer landing.** With the 350 ms slow part,
  the arm reaches the wall every cycle and LOCK now always ends at 90°.
  That confirms the earlier overshoot came from the arm starting out of
  place. The wall contact was a bit more than a light tap, so the fast
  part of UNLOCK was cut from 110 ms to 90 ms and deployed.
- **2026-11-07: tap comes from the slow speed.** Cutting the fast part made
  no visible difference to the tap. So the arm is already in the slow part
  when it reaches the wall, and the slow speed sets how hard it lands. The
  slow speed was lowered from 90 to 75, with its time raised from 350 ms to
  450 ms to cover the distance, and deployed. Risk: at 75 the motor may be
  too weak to push the arm all the way (it would hum and stop short).
- **2026-11-07: latch timings settled.** At speed 75 the tap is fine and the
  arm still reaches the wall. Final numbers:
  - LOCK: 215 ms at speed 150.
  - UNLOCK: 90 ms at speed 150, then 450 ms at speed 75.
  - `WALL_IS_M1A = true`.

  These go into the real safe sketch later.
- **2026-11-08: webcam view too zoomed in; resolution is not the fix.**
  The capture tool works with the real webcam (camera 0). At 640x480, two
  fingers filled most of the red square, so five spread fingers wouldn't
  fit. Some webcams crop their sensor at low resolutions, so camera 0 was
  tested at 640x480, 1280x720 and 1920x1080, using the engraved square
  inside the red tape as a ruler:

  | Setting | Square's width / frame | Square's height / frame |
  |---|---|---|
  | 640x480 | 67% | 76% |
  | 1280x720 | 50% | 77% |
  | 1920x1080 | 50% | 77% |

  The two 16:9 settings show the same area, and all three show the same
  desk from top to bottom. 640x480 only trims the left and right edges
  (4:3 is a narrower shape), so it is not a zoom.

  The crop box is square, so it can be at most as tall as the frame, and
  that height covers the same desk at every setting. A higher resolution
  would give more pixels of the same spot, not a wider view. It would
  also cost the UNO Q 3x (720p) or 6.75x (1080p) more pixels per frame to
  grab and shrink; 1080p would very likely be too slow to run live.

  Even now, the camera can't see the whole red square from top to bottom.
  Decision: keep 640x480 (no code change). Fix the view physically
  instead: raise or tilt the camera, or use a smaller square, so a spread
  hand fits inside the box. The UNO Q app must still use 640x480, the
  same as training.
- **2026-11-08: the camera switched picture shape partway through a
  session.** The first real session saved a crop box of size 360 at y=0
  and 80 class-2 photos. The next session gave 640x480 pictures, and the
  saved box no longer matched: the old photos show the whole engraved
  square with room around it, while the same box now shows only part of it.

  The cause: `capture.py` checked the picture size only on the first frame.
  That first frame was 640x480, so the config recorded 640x480. The camera
  then switched to a wide 640x360 picture, which shows more desk side to
  side. The giveaway is the box itself: auto-fit sized it to the live
  pictures, and size 360 at y=0 is exactly the full height of a 360-tall
  picture. So the photos and the saved box both belong to the 640x360 view.

  Fixes:
  - `hand_crop.py` now forces 640x480 and checks every frame
    (`check_frame_size`). `capture.py` stops with a clear error if the
    size is ever different, at startup or partway through.
  - `crop_config.json` keeps its picture size, and a box saved for any
    other size is refused (`box_from_config`). The old "stretch the box to
    the new size" fallback was removed, because a stretched box cuts out a
    different slice of the desk.
  - The 80 class-2 photos and the old `crop_config.json` were moved, not
    deleted, to `data_old_640x360/`. Git ignores that folder. The config
    went too because it was labelled 640x480 but its box was fitted to the
    640x360 view, so the new check would have wrongly accepted it.

  Checked: fake 640x360 and 1280x720 pictures are refused; a config saved
  for 640x360 is refused; the real camera sent only 640x480 for 3 s. The
  UNO Q app must force and check 640x480 the same way.

  Still possible: if the webcam ever crops its sensor while keeping the
  same 640x480 size, the size check can't see that. Check the preview
  against the red square at the start of each session.
- **2026-11-08: finger-counting network trained.**

  *Data.* 481 photos, all of Mohammed's hand, all with the new
  475-pixel box:

  | Class | 0 | 1 | 2 | 3 | 4 | 5 |
  |---|---|---|---|---|---|---|
  | Photos | 80 | 81 | 80 | 80 | 80 | 80 |

  Each class was recorded in under 2 minutes, in 7 to 18 bursts. So the
  80/20 split moves whole time-blocks to validation, not single photos. One
  class-1 photo shows only a fingertip at the edge (practically an empty
  square).

  *Model.* The network has 55,190 parameters.

  *First run* (Adam, step 0.001, stop after 15 epochs without
  improvement): best epoch 93.8%. But validation accuracy jumped between
  45% and 94% from epoch to epoch, and the training accuracy sometimes
  dropped suddenly too.

  *What didn't help:*
  - A smaller step (0.0003): 75%.
  - Halving the step whenever validation stalled: 72%. It shrank too early
    and training stalled around 60%.
  - Batch normalization after each convolution: typical 80%.
  - Twice the filters (16/32/64): typical 86%.

  All versions reach a lucky best epoch of 94–97% but average 80–86% over
  their last 10 epochs. The jumps come from the small, clumpy validation
  set: about 2 bursts per class, so 8 photos flip together. The data is the
  limit, not the network.

  *Dead filters.* 1 of 8, 2 of 16 and **18 of 32** filters never switched
  on for any photo. These are the warm-up's dead neurons again: with no
  gradient, they never learned. Kaiming starting weights plus a 0.1
  starting bias fixed it: 0 dead filters, with the same accuracy.

  *Final result:* best epoch 60, **94.8% (91 of 96)**, typical about 83%.
  - Mistakes: 1→0 once; 2→1 twice and 2→3 twice.
  - The confusion matrix shows no 4/5 mix-ups, but the best class-5 photo
    of the old run was only 69% sure when the thumb was cut off.

  *Live test.* The live window was checked on real webcam frames: the
  empty square gives "0" at 88–91%, and one guess takes 5 ms on the
  laptop. It has not been tried with a hand in front of the camera yet.

  *Not tested:* other people's hands and other lighting.
- **2026-11-08: retrained with evening photos.** In the live test, one
  finger was called "2" because of a finger shadow: the first session was
  daylight only. Mohammed took about 40 more photos per class in the
  evening, with shadows.

  *Data.* 721 photos (120 per class; 0: 80 + 40, 1: 81 + 39, and so on).

  *Split change.* With two sessions, 2 random blocks out of 10 could both
  land in one session, and the evening photos might not be tested. Now
  each session of each class is split on its own: 2 of 10 blocks go to
  validation. The daylight session is split first with the same seed, so
  its 96 validation photos are exactly the old ones. 48 evening photos are
  added (8 per class), which makes 144 in total.

  *Result:* best epoch 47, **95.8% (138 of 144)**, typical about **91%**
  (was 83%). Still 0 dead filters.

  | Validation photos | Daylight-only network | New network |
  |---|---|---|
  | Daylight (96) | 94.8% | 94.8% |
  | Evening (48) | **58.3%** | **97.9%** |

  - The old network's evening mistakes were mostly 3/4/5 mix-ups (5 → 4
    seven times, 3 → 4 five times): shadows look like extra or missing
    fingers.
  - The new network's daylight mistakes changed: 2 → 1/3 (4 times) is
    gone, and 3 → 2 (4 times, one burst of one sideways pose) is new. The
    daylight score is the same, but the mistakes are different.

  *Not tested yet:* the live test with a hand, and other people's hands.
- **2026-11-08: the lock, on the laptop first.** `04_unoq_app/laptop_lock.py`
  runs the whole code lock from the webcam, with the policy described in the
  04_unoq_app section.

  - *Tested in simulation:* 17 made-up guess sequences, all passed:
    - the right code unlocks; L locks; repeated digits 1-1-2 work
    - holding one digit for 4 s types it only once
    - not accepted: a 0.8 s hold, 80% confidence, or a hold broken by one
      unsure frame
    - a wrong code is a strike; 3 strikes lock out for 30 s, then reset
    - 15 s without progress returns to IDLE
  - *Real camera:* about 24 frames per second; the empty box reads "0" at
    97%. A full code hasn't been entered with a real hand yet.
  - *Motor link:* a web request through the USB cable, with a secret word
    (options and reasons in the 04_unoq_app section).
    - New UNO Q app `safe_app`: a small web server passes commands over the
      Bridge to a sketch with the tuned moves. The sketch moves only when
      asked; at power-up it homes the arm and locks.
    - Tested on the laptop against a stand-in board: unlock and lock
      accepted, a wrong secret refused, and a missing board reported in
      under a second (so the lock stays LOCKED).
    - 2 extra simulation tests: when the board doesn't answer, the lock
      neither shows UNLOCKED nor pretends to be shut (19 tests in all).
    - *Board test:* see the next entry.
- **2026-11-08: safe_app on the real board; USB not seen.**
  - *Deploy failed first:* "port 7000 is declared by multiple sources:
    arduino:web_ui, app.yaml". The web_ui brick already reserves port 7000
    for its web server, and `app.yaml` listed it a second time. Fixed with
    `ports: []` (the brick still opens 7000).
  - *Redeploy worked* over Wi-Fi: the sketch compiled and flashed, and the
    app started. At power-up the arm homed and locked.
  - *Commands tested over Wi-Fi*, all as intended:
    - status: "locked"
    - wrong or missing secret: refused
    - a GET to /unlock: not found (only POST works)
    - UNLOCK: busy, then unlocked; a second UNLOCK was ignored
    - LOCK: locked; a second LOCK was ignored
  - *USB:* adb found no device although the board is plugged in. The Mac
    lists only the webcam as a USB device, and the board's own USB port
    reports "not attached" (its adb service is running). Both ends see
    nothing, so the likely causes are a charge-only cable, a hub or dock,
    or the port.
  - *Wi-Fi as a fallback:* `Mohammed.local` answered in about 30 ms on home
    Wi-Fi. Not tested on campus Wi-Fi.
  - *Watched:* Mohammed watched an UNLOCK, a 3 s pause, then a LOCK sent from
    the laptop. The arm moved correctly, and the box ended up locked.
- **2026-11-08: USB data doesn't work; Wi-Fi fallback added.**
  - *Two cables:* with two different USB-C cables, the Mac still lists no
    Arduino device (nothing for arduino, uno, qualcomm or 2341), and adb
    sees nothing. The board powers up from the cable, and its USB service
    is running but reports "not attached". Not solved yet; the next
    suspects are the Mac's ports or the board's USB setup.
  - *Fallback:* `laptop_lock.py` now tries USB first, then
    `Mohammed.local` over Wi-Fi (`WIFI_HOST` setting). The secret word is
    still required, and the screen shows which link is in use.
  - *Tested with stand-in boards on the laptop:* USB is preferred when both
    answer; it falls back to Wi-Fi when USB is gone. A wrong secret is
    refused without trying the other link. With both gone, it shows "not
    connected".
  - *Found:* after the cable swap restarted the board, no app was running.
    The safe app has to be started again after every power cut.
- **2026-11-08: the screen shows the board's real state; USB works now.**
  - *Problem:* without the board, the screen still said LOCKED, but the
    real arm could have been open.
  - *Fix:* the big text now shows only what the board confirms: LOCKED,
    UNLOCKED, MOVING... or "UNKNOWN - board not connected". A background
    thread asks the board every second. In the stand-in test, the screen
    switched to UNKNOWN on the next check after the board disappeared.
  - *Sketch change:* the sketch now reports "busy" the moment it accepts a
    move. Before, the laptop could read the old "locked" in the instant
    before the move started, and wrongly think the board had locked itself
    again. A repeated UNLOCK or LOCK is still ignored (checked: a LOCK while
    locked returned "locked" and nothing moved).
  - *Tests:* 24 simulation tests passed, including the new board-following
    rules, plus 2 polling tests.
  - *USB:* during these tests, adb found the board over USB (with the
    second cable, after the board restarted), and the redeploy went over
    USB. `system_profiler` still lists nothing for it, so that check was
    misleading on this Mac; `adb devices` is the one to trust. Unknown why
    it failed before: possibly the cable was only half seated, or the board
    needed a restart with the new cable.
- **2026-11-08: the UNO Q runs the whole lock.**
  - *Setup:* the webcam is in the Arduino USB-C hub's USB-A port; the hub's
    PD port is fed by a 5 V / 2.4 A power bank. The board is reached over
    Wi-Fi.
  - *Camera on the board:* the board lists it ("icspring camera",
    `/dev/video0`) and offers 640×480. One test frame came back 640×480 and
    framed the red square like the laptop did. App containers may use it
    (they get the board's devices and the video group). OpenCV opens it
    through GStreamer, and every frame so far has been 640×480.
  - *Running the network:* see the 04_unoq_app section. PyTorch would be a
    ~1 GB install, and the board's OpenCV 4.13 has no ONNX runner (no `dnn`
    part). Plain numpy needs no install: 144 of 144 validation photos gave
    the same guess as PyTorch (scores within 0.00001). Camera, crop and
    network took 41 ms per guess on the board (24 per second).
  - *Rules:* moved to `lock_logic.py`, shared by the board and the laptop.
    New: an open palm held 2 s wakes the safe and locks it again, and only
    counts after a fist or an empty box. 28 simulation tests pass,
    including a code ending in 5 not re-locking at once.
  - *LED matrix and demo page added* (see the 04_unoq_app section).
  - *First run:* the board read the empty square as "1"/"2" at only
    50–70%, because a cable was lying in the square. Below 85%, nothing
    happens; with the cable gone, it should read "0".
  - *CPU:* the first version kept all 4 cores busy (389% CPU). numpy spread
    each guess over every core, and the loop guessed as fast as it could.
    Limited to one core and 10 guesses per second: 79%. Less load also
    means less current drawn from the power bank.
  - *Power bank:* the board did not restart during three startup moves
    (home, then lock) with the camera running; its boot time stayed the
    same. Unlock and lock with a real hand are not tested yet.
- **2026-11-08: a more forgiving open palm; measured on the board.**
  - *Problem:* waking with the open palm was sometimes slow.
  - *Measured:* the board now logs every guess, readable only with the
    secret word. Mohammed did 9 palm wakes, 2 palm locks and 2 code entries
    (about 8 guesses per second):
    - The palm was often read as "4" (thumb cut off or hand tilted), and
      the network was much less sure: 43% of palm guesses were below 85%,
      29% below 70%.
    - The longest unbroken run of sure "5"s in any hold was 0.0–1.5 s, so
      the old rule (2 s of unbroken 85% guesses) would hardly ever have
      woken the safe.
  - *Change, for the palm only:* it now counts when at least 80% of the
    guesses in the last 1.2 s say "5" at 70% or more. One bad guess no
    longer starts the wait over. This is safe because the palm can only
    wake or lock, never open.
  - *Result with the new rule:* 8 of 9 wake holds worked, after 1.0–4.5 s
    (most in 1–2.5 s); the one miss was read as "4" almost the whole
    time. Both palm locks worked.
  - *Tests:* 24 simulation tests pass. A steady palm wakes in about 1.1 s;
    with one bad guess in five, about 1.3 s.
  - *Digits, the same idea? Not recommended.* Replayed on the same
    guesses, the "most guesses" rule would have accepted each digit only
    about 0.3 s sooner. Slow digits aren't caused by single bad guesses:
    the network saw the intended digit only 19–28% of the time in those
    holds, and other digits came up at 85%+ up to 16 times in one hold. A
    looser rule wouldn't help much, and would make it more likely to
    accept a digit nobody meant, which costs a strike. Digits stay strict
    (85%, every guess, 1 s). The real fix is more training photos taken
    with the board's camera, especially open palms with the thumb near the
    edge and the slow digits.
  - *Power:* no board restarts through the two unlocks and two locks.
- **2026-11-08: third photo session, aimed at the board's weak spots.**
  - *Why:* the board's guess log showed the slow digits. The palm was read
    as 4. Digit 2 was read as 3 or 4. Digit 1 was sometimes read as 2.
  - *Photos:* the same webcam and stand, with the cable moved from the hub
    to the laptop. The camera hadn't moved: the red tape sat in the same
    place as in the board's view (0-pixel shift), and the crop box was
    unchanged. New photos per class 0–5: 40, 40, 60, 50, 50, 60 (300), in
    9–13 bursts each with a different pose (thumb near the edge, tilts,
    hand high and low, fingers spread and together). Total 1,020.
  - *Training:* `train.py` now also reports accuracy per session. The 144
    earlier validation photos stay in validation, plus 60 new ones.
    - Best: 91.2% (186 of 204). Typical: 87%, lower than before only
      because validation now includes the harder new photos.
    - On the new photos: 66.7% → 81.7%. The palm-read-as-4 mistakes went
      from 5 to 0. Daylight and evening are unchanged (93.8%, 97.9%).
    - Still wrong: fingertips at the very edge (1 → 0) and 2 fingers
      pointing down from the top edge (2 → 3 or 0).
  - *Board files:* `prepare_board_files.py` re-exported the network; numpy
    and PyTorch agree on all 204 validation photos. The movie overview was
    remade for the new network.
- **2026-11-08: the retrained network on the board, and a longer lock move.**
  - *Deploy:* the webcam went back to the hub without the camera moving:
    the board's view had a 0-pixel shift from before. The empty square
    read "0" at 96%.
  - *Same test as before* (palm wakes, code entries, palm locks), with the
    guess log:
    - Palm wakes: 9 worked, median 1.1 s (was 1.6 s).
    - Code entries: 5 attempts, 3 right. Accepted digits mostly took
      1–5 s (were 2–11 s), with one slow "2" at 13 s. Attempt 3 was a
      wrong code on purpose, and the strike worked.
    - **One real misread:** in attempt 2 the code's 5 was read as 4, at
      85%+ for a full second, which cost a strike. Session 3 fixed the
      open palm being read as 4, but a 5 held like a code digit can now
      tip the other way. To watch.
  - *Arm short of 90°:* the lock stopped at about 70–85°. LOCK_MS = 215 was
    tuned while the board ran on the laptop's USB power. On the power bank
    (through the hub) the motor is a bit slower. The safe app's LOCK_MS is
    now 240 ms; Mohammed confirmed about 90°. Unlock still reaches the wall
    (it runs long on purpose). The latch test sketch keeps 215 ms (laptop
    power). If the power source changes again, the lock angle will change
    too: the lock has no wall to stop against.
  - *Power bank:* no board restarts through this whole test (3 unlocks, 3
    locks, 2 deploys).
- **2026-11-09: tamper alarm with the MPU-6050.**
  - *Wiring:* VCC → 3.3V, GND → GND, SCL → SCL, SDA → SDA; the sensor is
    stuck flat on the floor of the box, away from the motor. The board
    restarted at 00:44, during the wiring.
  - *Reading it:* the sensor is on the microcontroller's I2C pins, so the
    sketch reads it, as in HW7's step-recorder. It checks both I2C buses.
    At 100 readings a second it keeps the peak "shake" (mg away from the
    recent average) and "turn" (°/s); Python asks for the peaks 10 times a
    second and keeps a 10-minute log (`/motion?secret=...`). The sketch
    ignores movement while the latch moves and for 1 s after.
  - *Calibration* (still, knocks, sliding/lifting/shaking, then trying the
    locked lid, a hand over the box and a hand on the lid): see the table
    in the 04_unoq_app section.
    - Threshold: shake ≥ 80 mg or turn ≥ 12°/s, about 3× and 6× the still
      box's noise. The gentlest lid try only reached 71 mg of shake but
      24°/s of turn, which is why rotation counts too.
    - Replaying the whole calibration log through the rule gave alarms for
      the firm knocks, sliding, shaking, every lid try and the resting
      hand, and none for the still box, gentle taps, the latch's own moves,
      or closing the lid while unlocked.
  - *Hiccups:*
    - The box was open when a deploy locked the latch, so the arm swung out
      under the open lid. Unlocked, closed the lid, locked again from the
      laptop.
    - After one restart the sketch didn't find the sensor (it looked only
      once, right at startup). It now waits 0.5 s first and retries every
      2 s until the sensor answers.
    - The web page didn't show the alarm the first time, because it was
      loaded before the update. After a reload it did. The board's status
      carried the 5 s countdown the whole time (checked by recording it).
      Reload the page after every deploy.
  - *Lock rules and network:* unchanged.
- **2026-11-09: alarm sound on the demo page.** While TAMPER ALERT shows,
  the page plays a short square-wave beep every 0.3 s, alternating
  1000 Hz and 750 Hz like a siren, and stops when the board's 5 s alarm
  ends. The sound is generated in the browser, with no file to download.
  Browsers allow sound only after a click, so a note asks for one and turns
  green ("Alarm sound on") once it's done. Only the page changed. It was
  copied onto the board in place, so the app didn't restart and the latch
  didn't move. Tested on the real box: a firm knock gave the banner and
  the beeping.
- **2026-11-09: the safe starts by itself at power-on.** App Lab starts
  the board's "default" app at boot. It was still HW7's Step Recorder; it is
  now the safe app (`arduino-app-cli properties set default ...`).
  - *Power test:* unplugged the power bank for 10 s, then plugged it back
    in. The board booted from scratch (new boot time 01:49) and started the
    safe app by itself. 60 s after power-on it answered "locked", with
    camera OK, motion sensor OK and the empty square read as "0" (95%). The
    arm homed and locked on its own.
  - *Finding the page elsewhere:* see "The lock on the UNO Q" (Mohammed.local,
    the iPhone hotspot on campus, or asking over USB). The board's known
    networks, in order: home, iPhone hotspot, Tufts_Robot, tufts_eecs.
- **2026-11-09: the network movie (06_movie).**
  - *Photo:* the movie needed a real full camera frame, but only the
    128 × 128 crops had been saved. The safe app was stopped over Wi-Fi.
    Then 49 frames were taken on the board with the same `hand_crop.py`
    (640 × 480 forced and checked) while Mohammed held up 2 fingers, and the
    app was restarted. The network read all 49 as "2"; the most confident
    and sharpest frame (98.3%) is `source_frame.png`.
  - *Making it:* Pillow draws each frame, and OpenCV writes the H.264 MP4.
    No new installs (there is no ffmpeg on the laptop). 2,850 frames, 95 s,
    3.4 MB, rendered in about a minute.
  - *Choices:* filter 3 was picked because on this photo its output is 63%
    negative, so ReLU visibly removes something. The worked spot is the
    filter's strongest answer on a finger edge. Edge spots, where the window
    hangs over the border, and the red tape were avoided.
  - *Fixed while checking stills:* Helvetica has no "→" (arrows now use the
    system font); a few labels overlapped; the maps looked washed out
    (colours now scale to the 99th percentile); and in the zoom, the
    enlarged pixels sat half a cell off the grid lines.
- **2026-11-09: the movie restyled as paper-cutout stop-motion.** The smooth
  version looked like slides, so the same 9 scenes and real numbers were
  redrawn as digital stop-motion (`make_stopmotion.py`), keeping every scene
  start time. The smooth version is kept as `how_the_network_works_smooth.mp4`.
  - *Background:* Mohammed's photo of paper on the desk was cleaned
    (`clean_background.py`):
    - cropped the left edge
    - removed the show-through printing, keeping the grain
    - smoothed the faint vertical bands (to std 0.39)
    - light left/right from 132/203 to 162/179
    - a light cream tint (average 227/218/198), darker than the white
      cutout borders
  - *Fonts:* Marker Felt and Noteworthy come with the Mac, so nothing was
    downloaded. Marker Felt has no × or →, so marker text writes "x" and
    the arrows are drawn by hand.
  - *Test first:* a 5-second convolution test. Fixed after looking at its
    stills:
    - crowded numbers (wider cells)
    - tape too long
    - the bias note covering a row of weights
  - *Mohammed's three tweaks:*
    - tape only on the corners, never over letters
    - true colours on the photo cutouts (the vignette and flicker now apply
      to the desk only)
    - the output visibly filling as the window hops: a matching output
      close-up fills one cell per hop, the newest cell outlined
  - *Final:* 1,140 frames at 12 fps = 95.0 s, 20.5 MB. On the contact sheet
    (two frames from every scene, taken from the finished MP4), the
    best-epoch flag overlapped the graph's legend; it was moved and the
    movie re-rendered.
