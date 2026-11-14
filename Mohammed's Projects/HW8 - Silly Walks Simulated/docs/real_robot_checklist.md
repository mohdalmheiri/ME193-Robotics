# Real-robot session (Monday after class): time-boxed plan

Every command runs from the HW8 folder (`Mohammed's Projects/HW8 - Silly Walks Simulated`). Prefix `../../.venv/bin/python` (left out below). Any robot script can be rehearsed with the simulator by adding `--fake`.

**ESSENTIAL** steps fit in about **55 minutes**. *OPTIONAL* steps are listed in priority order, so stop wherever the time runs out.

**Who does what:**
- **Mohammed:** laptop, commands, typing answers.
- **Julian:** the robot, measurements with a ruler.
- **A phone filming from straight above:** a third person, or a phone propped on something.

## The plan

| Clock | Step | Tag | Time | Done |
|---|---|---|---|---|
| before | [0. The night before](#0-the-night-before-not-in-the-slot) | ESSENTIAL | 15 min (not in the slot) | ☐ |
| 0:00 | [1. Connect](#1-connect) | ESSENTIAL | 5 min | ☐ |
| 0:05 | [2. Calibration](#2-calibration) (Mohammed) **while** [3. Julian measures the robot](#3-julian-measures-the-robot-in-parallel-with-step-2) | ESSENTIAL | 12 min | ☐ |
| 0:17 | [4. Stand check: dry run and Ctrl-C](#4-stand-check) | ESSENTIAL | 3 min | ☐ |
| 0:20 | [5. Drift test, 35 %, legs IN step](#5-and-6-drift-tests-at-35-) (filmed) | ESSENTIAL | 5 min | ☐ |
| 0:25 | [6. Drift test, 35 %, legs OUT of step](#5-and-6-drift-tests-at-35-) (filmed) | ESSENTIAL | 5 min | ☐ |
| 0:30 | [7. Policy runs ×3](#7-policy-runs) (filmed) | ESSENTIAL | 10 min | ☐ |
| 0:40 | [8. Baseline runs ×2](#8-baseline-runs) (filmed) | ESSENTIAL | 7 min | ☐ |
| 0:47 | [9. Demo rehearsal](#9-demo-rehearsal) | ESSENTIAL | 5 min | ☐ |
| 0:52 | [10. Save everything, weigh the robot](#10-save-everything-weigh-the-robot) | ESSENTIAL | 3 min | ☐ |
| 0:55 | ✂ **Running late? Cut here.** Everything below is optional | | | |
| | [O1. Speed under load](#o1-speed-under-load-does-the-hub-hold-the-speed) (regulated vs PWM) | *OPTIONAL* | 3 min | ☐ |
| | [O2. Lost-connection test](#o2-lost-connection-test) | *OPTIONAL* | 3 min | ☐ |
| | [O3. More runs](#o3-more-runs) (policy and baseline, up to 5 each) | *OPTIONAL* | 3 min per run | ☐ |
| | [O4. Drift tests at 100 %](#o4-drift-tests-at-100-), with a hand ready | *OPTIONAL* | 5 min | ☐ |
| | [O5. Julian's hand tests](#o5-julians-hand-tests) (`docs/hand_tests_sim.md` column) | *OPTIONAL* | 10 min | ☐ |

**If something breaks:**
- **A calibration step goes wrong:** rerun from that step with `robot/calibrate.py --from <step>`.
- **Bluetooth keeps failing:** skip to step 9 and rehearse the backup plan in `docs/demo_script.md`.

**Words used below:**
- **FRONT** = the end of the robot next to the motor axle. The body sticks out mostly *behind* the axle.
- **Legs at 0°** = pointing straight forward and flat, with the long arm (48 mm) in front of the axle.
- **Walking direction:** when a leg points down, its tip sweeps toward the robot's *back*, like a wheel rolling forward. The other direction flips the robot over.

---

## 0. The night before (not in the slot)

1. **Charge the Double Motor fully.** The motor specs are for 4.2 V.
2. **Run the tests.** Each one must say "passed":
   ```bash
   robot/tests/test_units.py
   robot/tests/test_policy.py
   robot/tests/test_safety.py
   robot/tests/test_real_robot_dryrun.py
   robot/tests/test_calibration.py
   robot/tests/test_calibrate.py
   ```
3. **Rehearse the calibration once** with a wrongly wired fake robot. It writes into a copy, not your config:
   ```bash
   cp robot/config.py /tmp/config_rehearsal.py
   robot/calibrate.py --fake --fake-hub upside-down --config /tmp/config_rehearsal.py
   ```
4. **Pack:**
   - the robot and the stand (a mug or a box, legs free)
   - tape for a straight start line
   - a tape measure **and a ruler**
   - the kitchen scale
   - this checklist printed, or open on a phone
5. **Check the policy:** `robot/model/policy_meta.json` must say `walk_straight_v2/.../model_799.pt`.

## 1. Connect

*ESSENTIAL, 5 min.*
- Laptop plugged in, Bluetooth on, hub switched on.
- Run the stand check from step 4 for 1 s: `robot/run_policy.py --real --seconds 1 --name connect`.
- **It works if** it prints a stop reason and a log file. A traceback about Bluetooth means: hub off and on, Bluetooth off and on, try again (3 tries maximum, then go to the backup plan).

## 2. Calibration

*ESSENTIAL, 12 min.* Mohammed runs this on the laptop; Julian handles the robot when asked, and measures it in between (step 3).

```bash
robot/calibrate.py
```

**What it does:**
- **Backup first:** it saves `config.py` to `robot/config_backups/` before changing anything.
- **Four steps:** it runs the four calibrations in order, asks their questions, and **writes each result into `robot/config.py` itself**. Every changed line gets a `# measured by calibrate.py on … (was: …)` note.

**Where the robot goes:**

| Step | Robot | What Julian does |
|---|---|---|
| 1 motor_direction | **On the stand**, legs free | Watch each leg spin at 20 %; say which leg (r/l) and whether it turned the walking way (y/n) |
| 2 leg_zero | **On the table**, motors off | Turn both legs by hand to 0° (Enter). Then turn the right leg so its long arm points straight up (Enter) |
| 3 measure_rpm | **On the stand** | Nothing: 25 / 50 / 75 / 100 % for 4 s each (16 s) |
| 4 imu_axes | **On the table** | Flat → front down (lift the back ~45°) → right side down (lift the left side) → flat → a quarter turn to the LEFT |

**If something goes wrong:**
- **A step warns:** it asks whether to keep the result. Answer **n** unless you know why, fix the set-up, then rerun from that step: `robot/calibrate.py --from leg_zero`.
- **The motor turns out slower than `POLICY_TOP_RPM` (110):** it offers to lower `POLICY_TOP_RPM` to 90 % of the motor's speed, inside the trained 80–140 rpm. Answer **y**.

**At the end it prints:**
- a before → after table;
- what percent a full action now is;
- a **suggested baseline percent** (the policy's average command on simulated robots with the new config). Write it here: **____ %**

**To undo everything:** copy the backup back. The exact `cp` command is printed at the start.

**Fallback if `calibrate.py` fails:** the four separate scripts still work, as before:
- `robot/calibration/motor_direction.py`
- `leg_zero.py`
- `measure_rpm.py`
- `imu_axes.py`

They print lines to paste into `config.py` by hand, in that order.

## 3. Julian measures the robot (in parallel with step 2)

*ESSENTIAL, no extra time.* While the laptop is busy, mainly during measure_rpm and between questions, Julian measures with a ruler. These numbers go into the CAD (Onshape) and the drawing afterwards.

**How to measure:**
- Body sizes: the plastic body only, not the legs or hubs.
- "Axle height": the robot standing on the table with both legs at 0° (straight forward, flat); measure from the table to the **centre** of the axle.
- **Hub sticks out:** how far each round motor hub stands out sideways from the flat body side.
- **Leg hole:** count the holes along the leg from the end of the **short** arm (that end's hole = 1); write which hole the axle goes through, and how many holes the leg has.

| What | Model now (for comparison) | Measured (mm) |
|---|---|---|
| Body length, front to back | ~80 (collision box) | |
| Body width, left to right (body only) | ~48 (collision box) | |
| Body height | ~30 (collision box) | |
| Axle height above the table, legs at 0° | 15.0 | |
| Hub diameter (right) | 25 | |
| Hub diameter (left) | 25 | |
| Right hub sticks out from the body side | ~8 | |
| Left hub sticks out from the body side | ~8 | |
| Right leg: axle hole number / total holes | short arm 16 mm, long arm 48 mm | ____ / ____ |
| Left leg: axle hole number / total holes | short arm 16 mm, long arm 48 mm | ____ / ____ |
| Leg length, tip to tip | 64 | |
| Leg thickness | ~8 | |
| Anything that looks different from the CAD (photo it) | | |

Take one photo from the front and one from the side, with the ruler in the picture.

## 4. Stand check

*ESSENTIAL, 3 min. Robot on the stand.*

1. **Dry run:** `robot/run_policy.py --real --seconds 5 --name standcheck`.
   - Both legs should spin the walking way.
   - It should stop by itself after 5 s and save a CSV in `robot/runs/`.
2. **Ctrl-C test:** start the same command, then press Ctrl-C after 2 s. **The motors must stop.**

## 5 and 6. Drift tests at 35 %

*ESSENTIAL, 5 min each, filmed from above.*

- **Set-up:** robot on the start line, facing along it. The phone films from straight above, starting before Enter.
- **Legs IN step:** `robot/calibration/drift_test.py --legs in --percent 35`. Both legs at 0°. It runs 10 s at 35 % (about the policy's top speed).
- **Legs OUT of step:** `robot/calibration/drift_test.py --legs out --percent 35`. Right leg at 0°; left leg a quarter turn ahead, long arm pointing straight up.
- **After each run, measure and type in:**
  - the straight-line distance from start to end (mm)
  - the sideways offset from the line (+ = right)
  - the turn angle from the video (+ = left)
- **Not 100 % first.** With the motor's published specs (~334 rpm), the simulated robot flips within about half a second at 100 % (`docs/hand_tests_sim_spec_*_100.md`). That is step O4, later, with a hand ready.

## 7. Policy runs

*ESSENTIAL, 10 min, filmed. These come first: the baseline needs the policy's average command.*

```bash
robot/run_policy.py --real --seconds 20 --name policy
```

- Do 3 runs. Start each on the line, facing along it.
- Write the stop reason printed for each:

  | Run | Stop reason | Notes |
  |---|---|---|
  | 1 | | |
  | 2 | | |
  | 3 | | |

- **Baseline percent:** the mean of `pct_r` / `pct_l` over the policy logs:
  ```bash
  ../../.venv/bin/python -c "import csv,glob,statistics as s; r=[x for f in sorted(glob.glob('robot/runs/*_real_policy.csv'))[-3:] for x in csv.DictReader(open(f))]; print(round(s.mean(abs(float(x['pct_r']))+abs(float(x['pct_l'])) for x in r)/2))"
  ```
  Write it here: **____ %** (compare with calibration's suggestion).

## 8. Baseline runs

*ESSENTIAL, 7 min, filmed.*

```bash
robot/run_policy.py --real --constant <percent from step 7> --seconds 20 --name baseline
```

Do 2 runs from the same start line. Measure them by hand like step 5.

## 9. Demo rehearsal

*ESSENTIAL, 5 min.* Do part 2 of `docs/demo_script.md` exactly as on Tuesday, timed:
1. Stand check.
2. Baseline, 15 s.
3. Policy, 15 s.

**Fill in the two blanks** in `docs/demo_script.md`:
- the baseline percent (from step 7)
- `POLICY_TOP_RPM`: read it from `robot/config.py`. It stays 110 unless calibration lowered it.

## 10. Save everything, weigh the robot

*ESSENTIAL, 3 min.*
- Weigh the whole robot on the kitchen scale: **____ g**
- Copy the phone videos to the laptop.
- `robot/runs/` keeps every CSV. Copy the ones the write-up cites to `docs/data/` later (`robot/runs/` itself is not committed).
- **Don't commit `config.py` in a hurry.** Look at its diff at home first.

---

## Optional, if time is left (in this order)

### O1. Speed under load: does the hub hold the speed?

*3 min.*
- Run `robot/calibration/measure_rpm.py --on-table` and let the robot walk about 1 m.
- Write down the speed under load. Nothing to paste.
- If it is much lower than on the stand at the same percent, the hub does **not** hold the speed. That is the "PWM" case in `docs/spec_motor_check.md`.

### O2. Lost-connection test

*3 min, robot on the stand.*
- Run `robot/run_policy.py --real --seconds 15 --name lostlink`. After 3 s, switch off the laptop's Bluetooth.
- **Do the legs stop by themselves?** The laptop cannot send a stop over a dead link, so this is the hub's own behaviour. Write the answer in the process log.

### O3. More runs

*3 min per run.* Up to 5 policy and 5 baseline runs in total, as in steps 7 and 8.

### O4. Drift tests at 100 %

*5 min.* Same as step 5 with `--percent 100`, and a hand ready to catch the robot. The simulator predicts a flip within about half a second.

### O5. Julian's hand tests

*10 min.* Fill in Julian's column in `docs/hand_tests_sim.md`.

---

## Afterwards (laptop, at home)

1. Check the `config.py` diff (`git diff robot/config.py`). Then commit it with the session's data.
2. **Simulator side**, with the measured rpm table already in `config.py` and the measured weight:
   ```bash
   robot/sim_hand_tests.py --motor regulated --percent 35 --body-mass-kg <motor weight in kg> --tag real_35
   ```
   - Use `--motor pwm` if O1 showed the speed sagging under load.
3. **Compare the real drift tests with the simulated ones:**
   ```bash
   robot/compare_drift.py --sim docs/data/hand_tests_sim_heading_real_35.csv --real docs/data/<drift_in>.csv docs/data/<drift_out>.csv
   ```
   This produces the real-vs-sim tables and plots.
4. Update the CAD and the drawing with Julian's measurements (step 3).
5. Write the results into `docs/process_log.md`.
