# Real-robot session: Julian, 2026-11-16

- **Who:** Julian, alone (laptop, robot and filming), following `docs/real_robot_checklist.md` → "Running the session alone".
- **Where:** on the floor. The surface is a smooth acrylic / plastic floor tile.
- **Laptop:** Mac. `.venv` at the repo root, Python 3.13.16, `robot/requirements.txt`.
- **Before the session:**
  - All 7 tests passed.
  - The `--fake --fake-hub upside-down` rehearsal printed 85 % and 49 %, as expected.
  - `policy_meta.json` = `walk_straight_v2/2026-11-13_18-36-30_v2/model_799.pt`.
- **Files:** every run log from `robot/runs/` is in this folder. Videos are on Julian's phone and not in git.

## Headline

| | Policy (4 real runs + 1 demo) | Constant 40 % baseline (3 real runs + 1 demo) |
|---|---|---|
| Distance in 20 s | **695–800 mm** in all 4 measured runs | −115 mm (looped back) or ~0 (stuck) |
| Final heading | **within 13°** of straight in every run | **71–296°** off, either way (2 runs left, 2 right) |
| Flips | none | none |
| Depends on the start leg phase? | **no** (walked from offsets −69° to +10°) | **yes**: legs in step → rocks in place; out of step → walks but curls left |

## Calibration

`robot/calibrate.py` was run three times; backups are in `robot/config_backups/` (not in git).

1. **12:27, full run.**
   - The imu_axes step warned: "gyro adds up to +0 but yaw changed +93 deg". The result was kept by accident.
   - **Cause:** the robot was turned *before* pressing Enter, and the gyro window only starts at Enter. The yaw still saw the turn, but the gyro saw nothing. Claude's instruction ("do the robot move first, then type") was wrong for that step.
   - The gyro itself streams fine: non-zero values appear in the connect log.
2. **12:35, `--from imu_axes`.** No warning, and the same values as run 1.
3. **12:39, `--from leg_zero`.** Julian wasn't sure the legs were flat at 0° the first time, so this pass redid leg_zero, measure_rpm and imu_axes.
   - Leg zeros moved by 4–5° from run 1: right 355.0 → 0.0, left 173.0 → 177.1.
   - rpm at 100 %: 167.6 → 165.8.
   - IMU values were identical.

**Final values (git `main` → this branch):**

| Name | Before (main) | After | |
|---|---|---|---|
| ROBOT_RIGHT_IS_LEGO | "right" | "right" | |
| UPRIGHT_PERCENT_SIGN | {right +1, left +1} | {right +1, left +1} | |
| ENCODER_SIGN | {right −1, left −1} | {right −1, left **+1**} | changed |
| LEG_ZERO_DEG | {0.0, 0.0} | {right **0.0**, left **177.1**} | changed |
| RPM_AT_PERCENT | placeholder, 334 rpm at 100 % | (25, 41.4), (50, 83.7), (75, 124.7), (100, **165.8**) | changed |
| RPM_MEASURED | False | **True** | changed |
| BODY_FROM_HUB | x:+x, y:+y, z:+z | x:**−y**, y:**+x**, z:+z | changed |
| ANGLE_UNIT_DEG | 1.0 | **0.1** | changed |
| PITCH / ROLL / YAW / GYRO_SIGN | +1 / +1 / +1 / +1 | +1 / +1 / +1 / +1 | |
| PITCH_ROLL_SWAPPED | False | **True** | changed |
| POLICY_TOP_RPM | 110 | 110 (not lowered) | |

- **A full policy action is now 66 % power.**
- **Suggested baseline percent:** 38 %. The real policy logs gave **40 %**, which is what the baseline runs used.
- **Warnings:** only the gyro one in run 1, which was redone cleanly. None remain.

## Runs

- **Distance** = straight-line distance, start to end.
- **Side:** + = right of the start line.
- **Turn:** + = left. "Hand" means estimated by Julian; "sensor" means the hub heading at the end of the log.
- **Start phase** = right − left leg angle at t = 0, from the encoders.

| # | Time | Log | Run | Start phase | Distance (mm) | Side (mm) | Turn hand / sensor (°) | Flipped | Stop |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 12:08 | `..._real_connect.csv` | connect, 1 s, on stand | | | | | | time limit |
| 2 | 12:42 | `..._12-42-24_real_standcheck.csv` | stand check 5 s | | | | | | time limit; both legs spun the walking way |
| 3 | 12:42 | `..._12-42-40_real_standcheck.csv` | Ctrl-C test | | | | | | Ctrl-C; motors stopped at once |
| 4 | 15:21 | `..._drift_in_35.csv/.json` | drift, legs IN, 35 %, 10 s | −2 (legs −3 / −1) | 120 | −70 | +60 / +59.2 | no | time limit |
| 5 | 15:26 | `..._drift_out_35.csv/.json` | drift, legs OUT, 35 %, 10 s | | 390 | −210 | +47 / +48.2 | no | time limit |
| 6 | 15:28 | `..._15-28-01_real_policy.csv` | policy 1, 20 s | +10 | 720 | +140 | +10 / +6.5 | no | time limit |
| 7 | 15:31 | `..._15-31-17_real_policy.csv` | policy 2, 20 s | −38 | 700 | +120 | −8 / −11.5 | no | time limit |
| 8 | 15:33 | `..._15-33-34_real_policy.csv` | policy 3, 20 s | −69 | 695 | +60 | −10 / −13.4 | no | time limit |
| 9 | 15:35 | `..._15-35-56_real_constant40_baseline.csv` | baseline 1, 40 %, 20 s | −103 | −115 (behind the start line) | −480 | +178 / +170.2 | no | time limit |
| 10 | 15:41 | `..._15-41-05_real_constant40_baseline.csv` | baseline 2, 40 %, 20 s | −3 | ~0 (stayed in place) | ~0 | +70 / +71.1 | no | time limit |
| 11 | 15:43 | `..._15-43-04_real_standcheck.csv` | demo rehearsal: stand check 5 s | +7 | | | | | time limit |
| 12 | 15:43 | `..._15-43-21_real_constant40_baseline.csv` | demo rehearsal: baseline 15 s | +89 | not measured | not measured | — / **−230.6** (turned right) | no | time limit |
| 13 | 15:43 | `..._15-43-46_real_policy.csv` | demo rehearsal: policy 15 s | +6 | not measured | not measured | — / −3.6 | no | time limit |
| 14 | 15:55 | `..._15-55-58_real_constant40_baseline_video.csv` | video: baseline 40 %, 20 s, legs in step | +7 | ~0 (spun near the start; video) | ~0 | — / **−295.7** (turned right) | no | time limit |
| 15 | 15:56 | `..._15-56-40_real_policy_video.csv` | video: policy 20 s, legs in step | −1 | 800 | +130 | — / +11.6 | no | time limit |

**Sensor headings count whole turns.** The hub's yaw wraps at ±180°, so the final sensor heading is unwrapped over the whole log. A first version of this table took only the last wrapped value. That gave +129.4 (row 12) and +64.3 (row 14) for two runs that really turned **right** by 231° and 296°. The video of row 14 confirms it: the robot spins clockwise near the start.

**Average commands (pct_r / pct_l):**
- Policy runs: 45.4 / 36.1, 42.4 / 35.9, 48.7 / 30.4, and 42.3 / 38.9 for the video run.
- The policy consistently drives the **right** leg harder, so on its own this robot would probably veer left. That fits both 35 % drift tests and 2 of the 4 constant 40 % runs; the other two turned right (see Surprises).
- Baseline percent from the 3 policy logs, using the checklist formula: **40 %**.

**Not done:** the optional steps O1–O5 (speed under load, lost-connection test, 100 % drift tests, hand tests).

## Julian's measurements vs the CAD

- **Measured:** by Julian with a ruler, in mm. Body sizes are for the plastic body only.
- **Model:** read from the simulator's model, `robot/model/scene.xml`. That is the CAD export the policy was trained on. Its collision boxes and hub cylinders are listed below. Distances are from the motor axle (the body frame's origin).

| CAD dimension | Model (mm) | Measured (mm) | Difference (mm) |
|---|---|---|---|
| Body length, front to back | 80 (box, half-size 40) | 80 | 0 |
| Body width, left to right | 48 (box, half-size 24) | 48 | 0 |
| Body height | 30 (box, half-size 15) | 30 | 0 |
| Front of the body to the axle | 15 (box centre 25 behind the axle, + 40 − 25) | 16 | +1 |
| Axle height above the floor, legs at 0° | 15.0 | 15 | 0 |
| Hub diameter, right / left | 25 / 25 (cylinder radius 12.5) | 25 / 25 | 0 / 0 |
| Hub sticks out from the body side, right / left | 8 / 8 (hub spans 24–32 from the centre) | 8 / 8 | 0 / 0 |
| Leg length, tip to tip | 64 (box, half-size 32) | 63 | **−1** |
| Leg thickness | 7.8 (box, half-size 3.9) | 8 | +0.2 |
| Leg pivot: short arm / long arm | 16 / 48 (leg box centred 16 from the axle) | hole 2 of 7 = 16 / 48 | 0 |

- **Every dimension matches within 1 mm.** The leg is 1 mm shorter than modelled, and the front of the body is 1 mm further from the axle. Both are inside what a ruler can tell.
- **Leg pivot:** hole 2 of 7 on a 1×8 Technic brick is 16 mm from the end. Both legs are identical.
- **Weight is the one real difference.** Julian's scale read **96 g** for the whole robot. The model has **105.6 g** (100 g body + 2 × 2.8 g legs), about 9 % too heavy.
  - The simulator comparisons below use a 90.4 g body, which brings the model's total to the measured 96 g.
  - The policy was trained with body mass randomized over ×0.6–1.6, so 96 g is well inside its range.

## Simulation vs reality

**How the simulator was set up.**
- It uses the calibrated `config.py` (measured rpm table, wiring, sensor conventions), the spec motor (`--motor regulated`, as the checklist says), and the measured weight (90.4 g body, 96 g total).
- **Drift tests:** `robot/sim_hand_tests.py --motor regulated --percent 35 --body-mass-kg 0.0904 --tag real_35`, then `robot/compare_drift.py`.
- **Filmed runs:** `robot/real_vs_sim_video.py`.
  - The sim robot starts with the real log's first leg angles.
  - Three kinds of robot are compared: the real robot (motion sensor), the nominal simulated robot, and 20 lopsided ones randomized as in training.

| Test | Measure | Real | Sim nominal | Sim lopsided: median (range) | Real inside the lopsided range? |
|---|---|---|---|---|---|
| Drift, legs in step, 35 %, 10 s | distance (mm) | 120 | 388 | 488 (286 to 980) | **no** |
| | sideways (mm) | −70 | 0 | −28 (−609 to 583) | yes |
| | turn (°, + = left) | +60 | 0 | −21 (−172 to 111) | yes |
| Drift, legs out of step, 35 %, 10 s | distance (mm) | 390 | 679 | 614 (285 to 843) | yes |
| | sideways (mm) | −210 | −22 | −212 (−673 to 666) | yes |
| | turn (°) | +47 | −16 | +23 (−148 to 105) | yes |
| Filmed baseline, 40 %, legs in step, 20 s | turn (°) | **−296** | −16 | −49 (−430 to 251) | yes |
| | distance | spun near the start | 748 mm forward | | |
| Filmed policy, 20 s | turn (°) | +12 | −2 | +0 (−10 to 14) | yes |
| | distance (mm) | 800 (other policy runs: 695–720) | **1586** forward | | |

**Where they are close:**
- **Steering.** The policy's heading wobbles about ±20–30° on the real robot. That's the same size and rhythm as in simulation (`real_vs_sim_heading.png`, right panel). The real final heading lands inside the simulated spread.
- **The trained behaviour transferred.** The policy walks the real robot straight, as it does the simulated ones.
- **Fixed-speed turning.** Every real turn, sideways drift and heading falls inside the range of the 20 lopsided simulated robots. The real robot behaves like *one* lopsided robot, not like the perfectly symmetric nominal one. The nominal robot barely turns: 0° to −16°.

**Where they differ:**
- **Distance: the real robot covers about half as much ground.**
  - Policy: 695–800 mm real vs 1586 mm simulated.
  - Drift out of step: 390 vs 679 mm.
  - **Drift in step: 120 vs 388 mm.** That's below even the shortest lopsided sim robot. In step, the real robot mostly rocks or spins in place; the simulated one walks.
- **We haven't tested why.** Likely suspects:
  - the smooth acrylic tile giving less grip than the model's friction;
  - the motor slowing under load (the rpm table was measured on the stand, and step O1 wasn't done);
  - leg–floor contact details.
- **Turn direction isn't predictable.** On the same robot, 40 % runs turned 170° and 71° left, and 231° and 296° right. The nominal sim can't predict which way a fixed-speed real run turns, only that it may turn a lot.

**Bottom line:** the sim gets the robot's shape and weight right and the policy's steering behaviour right. It overestimates how fast the robot moves over the ground by roughly 2× on this floor.

**Caveats for the videos:**
- The sync is automatic: the first frame where the start spot changes. Real t = 0 is at 2.8 s (baseline) and 2.6 s (policy) into the clips.
- The sim camera is matched to the phone by eye: 0.78 px/mm, from the body's 60 × 40 px.
- The phone was bumped slightly between about 12 s and 16 s of the policy video.
- The sim robot leaves the frame halfway through, because it walks about 2× as far. The scale was kept the same on purpose, so the distance difference is visible.

**Files:**
- `docs/media/real/real_vs_sim_baseline.mp4`, `real_vs_sim_policy.mp4`: real (left) | sim (right).
- `docs/media/real/real_baseline.mp4`, `real_policy.mp4`: the compressed phone videos.
- `docs/media/real/real_vs_sim_heading.png`, `docs/data/session_julian/real_vs_sim_runs.csv`: heading comparison for the filmed runs.
- `docs/drift_real_vs_sim.md`, `docs/media/drift_real_vs_sim_in.png`, `_out.png`: drift tests vs sim, from `compare_drift.py`.
- `docs/hand_tests_sim_real_35.md` (+ csv/png): the simulated drift tests with the measured config.

## Surprises

1. **The motor is about half as fast as its published spec.** It measured **165.8 rpm at 100 %** on the stand, against the 322–346 rpm published (checklist estimate ~330).
   - So a full policy action is **66 %** power, not the predicted ~33 %.
   - The suggested baseline percent is 38 %, not ~20 %.
   - The speed is still above `POLICY_TOP_RPM` = 110, so nothing was lowered.
2. **The left leg's zero is a half turn from the right's** (0.0° vs 177.1°). This was consistent across two leg_zero passes, so it's taken to be how the left leg is mounted, not an error.
3. **The constant-speed robot only walks if its legs start out of step.**
   - **In step:** drift-in went 120 mm, and baseline 2 stayed in place.
   - **Out of step:** drift-out went 390 mm, and baseline 1 looped about 170° left.
   - **The policy walked about 700 mm from every start phase.** For a fair demo, start the baseline with the legs in step (both at 0°).
4. **The constant-speed robot turns a lot, but not always the same way.** Both 35 % drift tests turned left (60°, 47°). At 40 %, two runs turned left (170°, 71°) and two turned right (231°, 296°). Every policy run ended between 13° right and 12° left.
5. **Hand turn estimates matched the hub's yaw** to within 1–4° on every run with both. This confirms the IMU calibration (YAW_SIGN, ANGLE_UNIT_DEG = 0.1).
