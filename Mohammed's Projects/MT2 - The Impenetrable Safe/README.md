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
  02_data_collection/           script that takes labeled photos of hands
  03_training/                  PyTorch CNN training (runs on the laptop)
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

A script that opens the webcam and saves photos labeled with how many
fingers are up, building the training set for the network.

### 03_training

The PyTorch code that trains the finger-counting CNN on the laptop and
saves the trained model file that the UNO Q app loads.

### 04_unoq_app

The App Lab app for the UNO Q: the Python side reads the camera, runs the
model and checks the code; the sketch side drives the latch motor when the
Python side says to.

### 05_hardware_tests/latch_motor_test

A small UNO Q app that only spins the latch motor: forward for 300 ms at
speed 150 (out of 255), wait 2 s, back for 300 ms, wait 2 s, repeat. The
swings are kept short on purpose: the latch arm is attached, and a longer
swing could turn it too far. `SPEED` and `MOVE_MS` at the top of
`sketch/sketch.ino` are the two numbers to tune.

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
the laptop. The motor starts moving 2 s after the app starts.

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
