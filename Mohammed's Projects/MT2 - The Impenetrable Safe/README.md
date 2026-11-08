# The Impenetrable Safe (MT2)

A laser-cut box that opens only for the right hand signals. A webcam watches
you hold up fingers, a PyTorch neural network counts how many (0 to 5), and
if you show the correct three-number code in order, an Arduino UNO Q drives a
small TT motor through a Cytron Maker Drive to swing a latch and unlock the
box. Show the wrong code and the latch stays shut. The project runs the whole
chain a robot needs, from seeing (camera), to deciding (neural network and
code check), to acting (motor and latch), on one small board.

> **Status:** in progress. The folder layout, the motor wiring and the motor
> test app are set up; the camera code and trained model are still to come. See the
> [build log](#build-log) at the bottom.

## How it works

### From one neuron to a full image network

The project is built in steps that each add one idea:

1. **One neuron** (`01_warmup_gradient_descent/`): a single neuron with a
   ReLU is fitted to V-shaped data by gradient descent, with every
   derivative written out by hand in Python and worked through in Excel.
   This shows the basic "guess, measure the error, nudge the numbers,
   repeat" loop that all neural network training uses. A second script
   fits the same data with a hidden layer of two neurons in PyTorch, for
   comparison.
2. **Many neurons that look at pictures** (`03_training/`): the same loop,
   run by PyTorch on thousands of numbers at once, trains a convolutional
   neural network (CNN). A CNN slides small pattern-finders over the image,
   so it can spot a finger wherever it is in the frame instead of only in
   one fixed spot.

### Training on the laptop, running on the board

Training a network takes a lot of computing, so it happens on the laptop.
The finished network is just a file of numbers, small enough to copy to the
UNO Q, where it only has to *use* what it learned (much less work than
learning it). The UNO Q has two brains: a Linux computer that runs the
camera and the network in Python, and a microcontroller that drives the
motor. The two talk over the board's built-in Bridge.

### Turning a shaky guess into a code

A camera network does not give one clean answer: it guesses every frame,
and the guess can flicker while your hand moves. The safe only accepts a
number once the guess stays the same for a set time, and it needs a pause
(no hand) between numbers, so a code with a repeated number like 3-3-1 can
still be entered. The exact timings will be tuned once the network is
trained.

### A latch with no position sensor

A TT motor has no sensor that says where it is. The latch is moved by
running the motor in one direction for a short, measured time, then
stopping. `05_hardware_tests/latch_motor_test/` exists to find that time and
the speed that swings the latch reliably without straining the motor.

## Hardware

- Arduino UNO Q, plugged into the laptop by USB-C
- USB webcam
- Cytron Maker Drive (2-channel motor driver; only channel 1 is used)
- TT gear motor driving the latch
- Laser-cut box and latch arm

### Wiring

| From | To | What it does |
|---|---|---|
| Maker Drive M1A (input) | UNO Q D9 | speed signal for one direction |
| Maker Drive M1B (input) | UNO Q D10 | speed signal for the other direction |
| Maker Drive GND | UNO Q GND | shared ground so the signals make sense |
| Maker Drive VB+ / VB- | UNO Q 5V / GND | motor power |
| Motor wires | Maker Drive M1A / M1B (output terminals) | the motor itself |

How the driver is told what to do: when D9 sends a speed signal and D10 is
off, the motor turns one way; swap them and it turns the other way; both
off and it stops. The "speed signal" is PWM: the pin switches on and off
very fast, and the share of time it is on sets the speed. Both D9 and D10
can do PWM on the UNO Q (checked in the board's own pin table, see the
build log).

## Files

```
MT2 - The Impenetrable Safe/
  README.md
  01_warmup_gradient_descent/
    annacode-v.tsv              the V data (120 points) from Anna's Code
    single_neuron.py            one ReLU neuron, gradients written by hand
    gradient_descent_5_iterations.xlsx   the same first steps as spreadsheet formulas
    two_neurons.py              hidden layer of 2 ReLU neurons, in PyTorch
    requirements.txt            Python packages for the scripts above
    *.png                       the data and the fits (made by the scripts)
  02_data_collection/
    capture.py                  webcam tool that takes labeled 0-5 finger photos
    hand_crop.py                the crop box and 128x128 resize, shared with training and the UNO Q
    crop_config.json            the saved crop box (created by capture.py)
    requirements.txt            Python packages for capture.py
    data/0 ... data/5           the photos (kept on the laptop only, not in Git)
    data_old_640x360/           80 early class-2 photos taken in the wrong camera mode (kept aside, not in Git)
  03_training/                  PyTorch CNN training (runs on the laptop)
    model.py                    the network (3 conv layers + 1 linear), shared by everything below
    train.py                    trains it: split, augmentation, early stopping, plots
    live_test.py                live webcam window with the network's guess and confidence
    feature_maps.py             pictures of what each layer "sees" (for the stop-action movie)
    requirements.txt            Python packages for the scripts above
    finger_cnn.pt               the trained network (made by train.py)
    loss.png, accuracy.png      training curves (made by train.py)
    confusion_matrix.png        which counts get mixed up (made by train.py)
    mistakes.png                the validation photos it gets wrong (made by train.py)
    feature_maps/               5 movie frames per class + overview.png (made by feature_maps.py)
  04_unoq_app/                  the final app that runs on the UNO Q
  05_hardware_tests/
    latch_motor_test/           UNO Q app that spins the latch motor both ways
      app.yaml                  the app's name tag for App Lab
      sketch/sketch.ino         the motor test code (runs on the microcontroller)
      python/main.py            empty Linux side that just keeps the app running
  media/                        photos, videos and screenshots
```

Empty folders hold a `.gitkeep` file only so Git keeps them; delete it once
the folder has real files.

### 01_warmup_gradient_descent

The warm-up, on the V example from Anna's Code (`output = 2·|x − 60|` plus
noise, x from 20 to 100). Both scripts first rescale the data to
x' = (x − 60)/40 and y' = y/100, so the numbers are small and centered on 0.

- `single_neuron.py` fits y_hat = ReLU(m·x' + b), starting at m = 1, b = 0
  (Anna's Code's default), with mean squared error and a learning rate of
  0.5. The gradients dL/dm and dL/db are written out as formulas, not left
  to PyTorch. It prints iterations 0 to 5 as a table, trains 200 epochs and
  saves `single_neuron_fit.png` (in the original units) and
  `single_neuron_loss.png`.
- `gradient_descent_5_iterations.xlsx` does the same iterations with live
  formulas: a `Data` sheet (x, y, x', y'), one `Iter` sheet per iteration
  with a row per point, and a `Summary` sheet. The learning rate and the
  starting m and b are the yellow cells on `Summary`; change one and every
  sheet updates.
- `two_neurons.py` trains a hidden layer of 2 ReLU neurons and a plain
  output neuron with PyTorch, from 10 random starts, keeps the best, and
  saves `two_neurons_vs_one.png` comparing it with the single neuron.
- `v_data_scatter.png` is a plain scatter plot of the data.

### 02_data_collection

The external webcam hangs off the laptop screen, looking down at a red
square taped on the desk. `capture.py` shows its live picture with a crop
box, which is lined up with the red square once and saved to
`crop_config.json`. Then each press of a number key 0-5 saves the inside of
the box, shrunk to 128x128 pixels, as `data/<number>/<person>_<number>_<time>.png`.
Holding the key saves about 5 photos per second, so the hand can move a
little between shots. The side panel counts each class's photos toward a
goal of 80 per class per person, so the classes stay balanced. Class 0 is a
fist **or** an empty square; the lock will use it as the pause between
code digits.

Two rules shape the tool:

- **The same camera for training and for the safe.** Each camera sees
  color, brightness and sharpness a little differently, so `--list`
  helps pick the external webcam and tells it apart from the laptop's
  built-in camera and from iPhones (Continuity Camera).
- **The same crop for training and for the safe.** `hand_crop.py` is the
  only code that cuts and shrinks the picture, and the training code and
  the UNO Q app will import it too, with the same `crop_config.json`. A
  network only recognizes the kind of picture it practiced on; a box a few
  pixels off on the safe would quietly make it guess worse.
- **The same picture size, always 640x480.** The webcam shows a different
  slice of the desk at a different picture shape, so the tool forces
  640x480 and checks every single frame. If the size is ever different, it
  stops with an error instead of saving photos. `crop_config.json` records
  the picture size its box was made for, and the tool refuses a box saved
  for any other size. The UNO Q app must force and check 640x480 the same way.

The photos stay out of Git (hundreds of pictures, including friends'
hands); a sample strip goes in `media/` (`capture.py --samples`).

### 03_training

The PyTorch code that trains the finger-counting CNN on the laptop and
saves the trained network (`finger_cnn.pt`) that the UNO Q app will load.

**The network** (`model.py`) follows the professor's hint: three
convolution layers, each followed by ReLU and 2x2 max pooling, then one
linear layer with 6 outputs.

- **Convolution:** each filter is a 3x3 pattern detector that slides over
  the whole photo.
- **Max pooling:** halves the picture after each layer.
- **Filter counts:** 8, then 16, then 32, while the picture shrinks
  128 → 64 → 32 → 16.
- **Final layer:** weighs the last 32x16x16 = 8,192 numbers into six
  scores.

It has 55,190 parameters (about 216 KB) and takes about 13 million
multiply-adds per photo: 5 ms per guess on the laptop, light enough for the
UNO Q.

**Training** (`train.py`):

- **Split:** 80% training and 20% validation, the same share of every
  class and of every capture session (daylight and evening), with a fixed
  seed. Photos were taken in bursts of near copies, so each session of each
  class is cut in time order into 10 blocks, and 2 whole blocks go to
  validation. Otherwise nearly every validation photo would have a twin in
  training, and validation would test memory rather than understanding.
- **Augmentation, training photos only:** each time a training photo is
  used, it is randomly rotated (±15°), shifted (±8%), brightened or darkened
  (×0.8–1.2), and mirrored half the time. Real hands are never at exactly
  the same angle, spot or lighting, and mirroring teaches left hands from
  right-hand photos. Validation photos are never changed, because they
  stand in for the real camera: changing them would measure the network on
  pictures the safe will never see.
- **Loss and optimizer:** cross-entropy loss (it punishes confident wrong
  guesses the most), and Adam at a step size of 0.001.
- **When to stop:** training stops when validation accuracy hasn't
  improved for 30 epochs, and the best epoch is kept.
- **Starting values:** "Kaiming" starting weights with a small positive
  bias, so no filter starts out dead (see the build log).

**Prepared the same way everywhere:** photos are turned into network input
by `hand_crop.to_network_input`, the same function that `live_test.py` and
the UNO Q app use. Live frames go through `hand_crop.frame_to_network_input`,
which checks the 640x480 size, crops the saved box and shrinks it.

**Results** (721 photos of one person's hand, in daylight and evening
light with finger shadows; 144 for validation):

![training curves](03_training/accuracy.png)
![confusion matrix](03_training/confusion_matrix.png)

- **Best epoch:** 95.8% on validation (138 of 144).
- **Typical:** about 91% (average of the last 10 epochs, 86–94%). The
  best epoch is partly luck; expect the typical number on new photos.
- **By lighting:** 94.8% on daylight photos and 97.9% on evening photos.
  The daylight-only network scored just 58% on the evening photos, so the
  evening session is what fixed the shadow mistakes.
- **Mistakes:** 4 of the 6 are one burst of the same pose: 3 fingers lying
  flat from the side with the top finger partly out of the box, called 2.
  The other two are 1 → 0 (one finger poking in from the edge) and 0 → 1
  (a fist at the edge of the box, in evening light).
- **Not tested on other hands:** every photo is the same hand, so friends'
  hands will probably do worse.

**What each layer sees** (`feature_maps.py`): for each class, the photo and
the most active map of each layer. Layer 1 still looks like the photo,
layer 2 cuts out the fingers, and layer 3 is a blocky outline of the
finger shapes.

![feature maps overview](03_training/feature_maps/overview.png)

### 04_unoq_app

The App Lab app for the UNO Q: the Python side reads the camera, runs the
model and checks the code; the sketch side drives the latch motor when the
Python side says to.

### 05_hardware_tests/latch_motor_test

A small UNO Q app that only swings the latch arm. UNLOCKED means the arm is
folded back against the box wall; LOCKED means it sticks straight out
(90°). The sketch first swings to the wall, then repeats: wait 3 s, LOCK,
wait 3 s, UNLOCK.

- **LOCK** runs 215 ms at speed 150 (out of 255).
- **UNLOCK** runs 90 ms at speed 150, then 450 ms at speed 75. Slowing
  down for the second half lets the arm reach the wall gently; the slow
  part is deliberately long, so the arm always gets there and leans on it.

The motor has no position sensor, so UNLOCK runs a little longer than
needed and the arm presses gently on the wall. The wall stops it in the
same spot every time, so small timing errors can't build up into drift.

Numbers to tune at the top of `sketch/sketch.ino`:
- `SPEED` and `LOCK_MS`
- `UNLOCK_FAST_MS`, `SOFT_SPEED` and `UNLOCK_SOFT_MS`
- `WALL_IS_M1A`: which motor pin turns the arm toward the wall
- `DIRECTION_CHECK`: when `true`, the sketch makes one swing out and one back, then stops

### media

Photos and videos of the build and the safe opening.

## Setup and run

### Warm-up (laptop)

From the repo root, with the shared virtual environment:

```
source .venv/bin/activate
pip install -r "Mohammed's Projects/MT2 - The Impenetrable Safe/01_warmup_gradient_descent/requirements.txt"
cd "Mohammed's Projects/MT2 - The Impenetrable Safe/01_warmup_gradient_descent"
python single_neuron.py
python two_neurons.py
```

Each takes a few seconds; the plots are rewritten in the same folder. The
Excel file needs nothing installed: open it in Excel, which recalculates
it on opening. (Previewers that don't calculate, like Quick Look, show the
formula cells empty.)

### Data collection (laptop)

From the repo root, with the shared virtual environment, and the external
webcam plugged in:

```
source .venv/bin/activate
cd "Mohammed's Projects/MT2 - The Impenetrable Safe/02_data_collection"
python capture.py --list                              # find the webcam's number
python capture.py --camera 1 --person mohammed        # 1 = the number from --list
python capture.py --samples --person mohammed         # sample strip for media/
```

Keys (click the preview window first): `w a s d` move the box (Shift for
bigger steps), `[ ]` shrink and grow it (`{ }` for bigger steps), `f` fits
it to the red square, `c` saves it, `0`-`5` save photos, `q` or Esc quits.
Number keys are refused while the box has unsaved changes.

### Training and live test (laptop)

From the repo root, with the shared virtual environment. Training takes
about 3 minutes on the laptop's processor; the live test needs the webcam
and a saved crop box.

```
source .venv/bin/activate
cd "Mohammed's Projects/MT2 - The Impenetrable Safe/03_training"
python train.py            # trains and saves finger_cnn.pt and the plots
python live_test.py        # live window: guess + confidence (q or Esc quits)
python feature_maps.py     # movie frames in feature_maps/
```

The same seed gives the same network every time. In the live window the
guess is green when the network is at least 80% sure, orange when it isn't.

### Latch motor test

The app is linked into the local `ArduinoApps` folder as `latch-motor-test`
(a shortcut pointing to `05_hardware_tests/latch_motor_test/`), so the
usual deploy tool can find it. With the UNO Q plugged in by USB-C:

```
cd ~/Documents/GitHub/ArduinoApps
export PATH="$HOME/Library/Arduino15/packages/arduino/tools/adb/32.0.0:$PATH"
python3 tools/deploy.py latch-motor-test
```

The `export` line lets the deploy tool find `adb` (the USB link to the
board), which App Lab installed but didn't add to the terminal's search
path. The board compiles the sketch itself, so nothing else is needed on
the laptop. The motor starts moving 5 s after the app starts. Without USB,
`deploy.py` uses the board's Wi-Fi address instead.

To stop it:

```
python3 tools/deploy.py --cmd "arduino-app-cli app stop /home/arduino/ArduinoApps/latch-motor-test"
```

The rest will be filled in as each part is finished.

## Tuning and notes

### Why one neuron fits only one side of the V

A ReLU neuron draws a hockey stick: flat at 0, then one straight ramp. It
can bend once, but a V needs two ramps, so the best it can do is one side.
It ends up on the right side because it starts at m = 1: a positive slope
puts the ramp on the right (starting at m = −1 would give the left side).

It then never moves over to the left points, even though they cause almost
all of the remaining loss (0.0947 of 0.0950). Those points sit on the
neuron's flat part, where ReLU's slope (`active`) is 0, so they add nothing
to dL/dm or dL/db: gradient descent gets no signal from them at all. That
is why the loss curve drops fast and then goes flat at 0.095. With two
hidden neurons, two hockey sticks are added together, which can make both
ramps of the V. The same `active = 0` problem is what traps the two-neuron
starts that get stuck: a neuron that is flat for every point gets no
gradient and stops learning.

### Build log

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
