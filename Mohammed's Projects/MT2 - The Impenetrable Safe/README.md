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
   ReLU is fitted to data by gradient descent, worked through by hand in
   Excel. This shows the basic "guess, measure the error, nudge the
   numbers, repeat" loop that all neural network training uses.
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
  01_warmup_gradient_descent/   single neuron + ReLU fit: Excel sheet and plots
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

The warm-up: one neuron with a ReLU fitted by gradient descent in Excel,
with plots of the fit and of the error going down step by step.

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
