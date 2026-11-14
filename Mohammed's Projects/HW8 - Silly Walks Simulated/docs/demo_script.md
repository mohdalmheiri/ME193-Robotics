# Class demo script (Tuesday morning)

Every command runs in a terminal from the HW8 folder (`Mohammed's Projects/HW8 - Silly Walks Simulated`).

Order:
1. The sim demo, about 2 min.
2. The real robot, about 3 min.
3. The backup plan, if Bluetooth or the viewer fails.

## Before class

**The night before (Monday, after calibration):**

1. Fill in the two blanks in part 2 below from Monday's calibration:
   - the baseline percent
   - whether `POLICY_TOP_RPM` stays at 110
2. Charge the Double Motor to full; the motor specs are for 4.2 V.
3. Rehearse once: run the sim demo, then do one real run at home.

**Tuesday morning, about 10 min before:**

1. Plug in the laptop and turn Bluetooth on.
2. Open `docs/media/` in Finder. The backup videos and plots are there.
3. Run the tests. Both must say "passed":
   ```bash
   ../../.venv/bin/python robot/tests/test_demo.py
   ../../.venv/bin/python robot/tests/test_real_robot_dryrun.py
   ```
4. Prepare the floor:
   - a clear strip, about 1.5 m long
   - a tape start line
   - the stand (a mug or box)
   - someone ready to catch the robot

## 1. Sim demo, about 2 min

```bash
../../.venv/bin/mjpython robot/demo_live.py
```

Use `mjpython`, not `python`. A MuJoCo window opens. Make it full screen (green button) before the robots start moving far; the run lasts 15 s. SPACE pauses, and closing the window ends the demo. Add `--loop` to keep it repeating while people come in.

**What the audience sees:** two copies of the **same** lopsided robot, with the same masses, friction, motors and Bluetooth delay. Both start on the green line.
- **Left, orange: baseline.** Both motors run at one constant speed (19%).
- **Right, blue: trained policy.**

**What to say:**
- "Real robots are never symmetric. Training randomized friction, mass, motor strength and delays, so the policy learned to walk straight on robots it has never seen."
- "Both robots get the same motor speed on average. The orange one just runs both legs at that speed, and it curves off."
- Point at the leg commands in the text box: the blue robot changes its two legs separately to steer back.
- **Say this:** "I picked this robot as a clear example; not every robot curves this much." Then show the overall result over 100 random robots: **`docs/media/eval_v2_dt0.002_paths.png`**.
  - Baseline: heading error 94° on average.
  - Policy: 7° on average, with 0 flips in 100.
  - In 20 s, the policy walked 1.6 m on average and the baseline only 0.4 m.

**If there's time:** run `--seed 34`. That robot curves the **other** way, and the policy still walks straight.

## 2. Real robot, about 3 min

**Calibration values (fill in Monday night):**
- Baseline percent, from `pct_r` / `pct_l` in Monday's policy log: **`____ %`**
- `POLICY_TOP_RPM` in `robot/config.py`: **`____ rpm`** (110 unless the calibration changed it)

**Steps:**
1. **On the stand** (legs in the air, 5 s). Both legs must spin the walking way and stop by themselves.
   ```bash
   ../../.venv/bin/python robot/run_policy.py --real --seconds 5 --name demo_standcheck
   ```
2. **Baseline on the floor.** Put the robot on the start line, facing along it.
   ```bash
   ../../.venv/bin/python robot/run_policy.py --real --constant ____ --seconds 15 --name demo_baseline
   ```
3. **Policy on the floor.** Start from the same line and direction.
   ```bash
   ../../.venv/bin/python robot/run_policy.py --real --seconds 15 --name demo_policy
   ```

- **Ctrl-C** stops the motors at any time.
- The run also stops by itself if the robot tips past 70° or the sensors go silent. The reason it stopped is printed.
- Keep a hand near the robot.
- Each run saves a CSV in `robot/runs/`.
- **Be honest if it curves:** the real robot is not the simulator.
  - The motor is ~2.5× faster than the simulated one, so a full action is capped at 110 rpm (about 33%).
  - Hub latency is a guess until it's measured.

## 3. Backup plan

**If Bluetooth won't connect:**
1. Turn the hub off and on.
2. Turn the laptop's Bluetooth off and on.
3. Run the stand check once more.
4. **If it still fails, stop trying** and show the videos:

| Order | File in `docs/media/` | What it shows |
|---|---|---|
| 1 | `demo_side_by_side.mp4` | Exactly the live sim demo: the same robot (seed 6), 15 s, baseline vs policy. Use this if the MuJoCo window won't open either |
| 2 | `eval_v2_dt0.002_paths.png` | **The overall result**: 100 random robots seen from above (left: baseline, middle: a simple steering controller, right: the policy) |
| 3 | `eval_v2_dt0.002_baseline.mp4`, then `eval_v2_dt0.002_policy.mp4` | One typical robot in the training simulator (MJLab), filmed from behind |
| 4 | `spec_motor_paths.png` | Only if someone asks about the real motor: the policy still walks straight with the published motor specs and an 80 g body |
| 5 | Monday's phone videos of the real robot | The real runs, if they worked |

**If the viewer window doesn't open:** check that the command uses `mjpython`, not `python`. If it still won't open, play video 1.

**Remaking the backup video**, about 1 min, no window:
```bash
../../.venv/bin/python robot/demo_live.py --record docs/media/demo_side_by_side.mp4
```
