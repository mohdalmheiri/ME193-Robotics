# Behavior Cloning Navigation (HW9)

A wearable guide that walks someone to Nolop without ever finding out where they are.
It doesn't use GPS or Wi-Fi to find its position. It only knows two things about the
walk so far: how many steps the person has taken since the last turn, and how many turns
they have made. A trained step counter on the ankle and a gyroscope at the waist measure
these, on an Arduino UNO Q. The navigation itself isn't programmed by hand. It is learned
by **behavior cloning**: we walk the route ourselves, press what we are doing on a phone
("straight", "left", "right", "stairs", "arrived"), and a policy learns to give the same
instruction in the same situation. The interesting part is doing this with very little
data. We are allowed at most 10 full walks in total, for both partners together, including
correction walks. That means cleaning the labels before training matters as much as the
model. For example, people press "turn" a moment after they start turning, so the label
lands late. The board runs everything and serves the phone page itself, so no laptop or
internet is needed on the walk.

> **Status (2026-11-17):** folder and plan set up. No board code, data or policy yet.
> Sections below describe the planned design; [docs/process_log.md](docs/process_log.md)
> records what changes as we build it.

## How it works

**Sensing (on the UNO Q)**
- **Steps:** an MPU-6050 on the right lower leg, near the ankle. We're starting with
  Mohammed's HW7 step counter ([HW7 - How Many Steps](../HW7%20-%20How%20Many%20Steps/README.md)),
  which already runs on the board in plain numpy, to be confirmed with Raph. Raph's
  stride-counting CNN is the alternative we're comparing it with (see Credits).
- **Turns:** a second MPU-6050 at the waist (I2C address 0x69, AD0 tied to 3.3 V). Neither
  sensor has a compass, so a turn is found by adding up the gyro's turning rate over time.
  The rotation is measured around the direction of gravity, so it still works if the
  sensor sits tilted on the belt. A turn is counted when the heading changes by a large
  angle (the threshold is set from the route's real turns) within a couple of seconds. The heading itself slowly drifts over a long walk, so
  the policy never uses it directly. It only uses the number of turns.
- **Stairs (optional):** a small classifier that says "on stairs" or not.

**What the policy sees and does**

| Observation (input) | Action (output) |
|---|---|
| steps since the last turn (or meters since the last turn: both are saved, to be compared) | Straight |
| turns so far (left, right) | Left |
| on stairs (yes / no) | Right |
| | Stairs |
| | Arrived |

**The policy: a lookup table first.** This follows the
[AnnaCode Table Cloner](https://chrisbuerginrogers.github.io/ME193-Robotics/Public%20stuff/AnnaCode/cloner.html).
During demonstrations, every situation the walker is in gets a tally of the actions they
chose there. When navigating, the board gives the most common action for the current
situation. If that exact situation never came up, it uses the closest one that did. The
whole policy is a table you can read, so it is easy to check what it learned. We'll try a
small neural net only if the table isn't good enough.

**Cleaning the labels before training**
- Shift each turn label a few steps earlier, to undo the walker's reaction delay.
- Choose how many steps before a turn the instruction should appear, so a new walker has
  time to react.
- Fix the label that stays on for a step after a turn ends (a known bug in the page).

**Corrections (DAgger)**
- On a correction walk, the policy guides. When it gives a wrong instruction, the walker
  presses the right one.
- The corrected moments are added to the training data, and the table is rebuilt. This
  teaches the policy situations the demonstrations never showed, such as a missed turn.

**The phone page**
- The board serves the page itself (the App Lab `web_ui` brick, port 7000), as in HW7.
- The phone joins the board over a phone hotspot. Wi-Fi is only the link between phone
  and board; it is never used to find where the walker is.
- Two tabs: **Record demo** (label a demonstration) and **Navigate + correct** (follow
  the policy; with "Save my corrections" ticked, every correction tap is saved for DAgger).
- It reads the board's state from `GET /api/state`: `steps`, `distance_m`, `turns_left`,
  `turns_right`, `steps_at_last_turn`, `distance_at_last_turn`, `heading_deg`,
  `on_stairs`.
- Before every walk it calls `GET /api/reset` (with who is walking and which kind of
  walk), and the walk only starts once the board answers `{"ok": true}` with its walk
  number, so each walk's counts start at 0.
- It sends every saved row to the board (`POST /api/rows`). If the board doesn't answer,
  the rows wait on the phone, even through a page reload, and go out in order when it
  answers again.
- If the board stops answering, a warning appears on both tabs and the instruction is
  greyed out until it answers again.
- The board saves each walk as one CSV; the phone's download is a backup. The columns are
  explained in [data/README.md](data/README.md).

## Hardware

- Arduino UNO Q, on a USB power bank
- 2 × MPU-6050 on one I2C bus: ankle at 0x68 (right lower leg, as in HW7), waist at 0x69
- A phone for the page and the hotspot
- The route: start point still to be decided, ending at Nolop

## Files

```
HW9 - Behavior Cloning Navigation/
├── README.md
├── uno_q/          the board app: sensing, policy and the phone page (own README)
│   └── assets/     the phone page
├── training/       label cleanup and policy training (laptop)
├── data/           recorded walks, their log and the recording checklist
├── docs/           process log: what we tried, what failed, what we figured out
└── media/          plots and images
```

| File | What it does |
|---|---|
| [uno_q/README.md](uno_q/README.md) | What the board app does and how to deploy it |
| [uno_q/app.yaml](uno_q/app.yaml) | App Lab settings: name, port 7000, web page brick |
| [training/requirements.txt](training/requirements.txt) | Laptop packages for label cleanup and training |
| [data/README.md](data/README.md) | Walk file naming, CSV columns and the 10-walk log |
| [data/RECORDING_CHECKLIST.md](data/RECORDING_CHECKLIST.md) | Step-by-step for testing the counter and recording each walk |
| [docs/process_log.md](docs/process_log.md) | Dated record of decisions and results |

## Setup and run

Not ready yet: the board code is next. The plan follows HW7:

1. Training on the laptop uses the repo's `.venv`:
   `pip install -r "Mohammed's Projects/HW9 - Behavior Cloning Navigation/training/requirements.txt"`
2. The board app is deployed from the ArduinoApps kit through a symlink to `uno_q/`.
3. On the walk, the phone opens the address that scrolls on the LED matrix.

## Tuning and notes

- **Walk budget:** 10 full walks at most, both partners together, corrections included.
  The table in `data/README.md` is the official count, not the page's counter.
  Short counted test walks of the step counter aren't full route walks, so they don't
  use up the budget. The log is in [data/README.md](data/README.md).
- **Step counter on a second person:** the HW7 counter has only been trained on
  Mohammed's walking and only tested on a straight 20 m course. Testing it on Raph's
  walking, and on walks with turns, is the first item in the recording checklist.
- **Long sensor wire:** the board and the ankle sensor sit together, as in HW7, so the
  waist sensor needs the long wire. I2C is meant for short wires, so check this early.
- **Board as its own Wi-Fi network:** possible, but while it is on, the laptop can't reach
  the board to deploy. The phone hotspot (already set up on the board) is the plan.
- **Still to decide:** start point, the exact route, and whether it stays inside a
  building or crosses campus.

## Credits

- **Raph's step counter**
  ([How many steps](https://github.com/RaphLemSol/ME193/tree/main/How%20many%20steps)):
  an ensemble of 1-D CNNs that finds each stride in the ankle data. It is the alternative
  to the HW7 counter that we're comparing; its board app streams the IMU over MQTT to a
  laptop running PyTorch.
- **Mohammed Almheiri:** the HW7 step counter and board app this builds on, and the
  HW9 setup so far.
- **Both partners** walk and label the route; the policy is trained on both partners' walks.
- The lookup-table policy follows the course's AnnaCode Table Cloner example (linked above).
