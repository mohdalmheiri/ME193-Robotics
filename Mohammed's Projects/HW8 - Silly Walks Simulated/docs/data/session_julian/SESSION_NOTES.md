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

| | Policy (5 real runs + 1 demo) | Constant 40 % baseline (3 real runs + 1 demo) |
|---|---|---|
| Distance in 20 s | **695–800 mm** in all 4 measured runs | −115 mm (looped back) or ~0 (stuck) |
| Final heading | **within 13°** of straight in every run | **64–170° left** in every run |
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
| 12 | 15:43 | `..._15-43-21_real_constant40_baseline.csv` | demo rehearsal: baseline 15 s | +89 | not measured | not measured | — / +129.4 | no | time limit |
| 13 | 15:43 | `..._15-43-46_real_policy.csv` | demo rehearsal: policy 15 s | +6 | not measured | not measured | — / −3.6 | no | time limit |
| 14 | 15:55 | `..._15-55-58_real_constant40_baseline_video.csv` | video: baseline 40 %, 20 s, legs in step | +7 | not measured | not measured | — / +64.3 | no | time limit |
| 15 | 15:56 | `..._15-56-40_real_policy_video.csv` | video: policy 20 s, legs in step | −1 | 800 | 130 (direction not noted) | — / +11.6 | no | time limit |

**Average commands (pct_r / pct_l):**
- Policy runs: 45.4 / 36.1, 42.4 / 35.9, 48.7 / 30.4, and 42.3 / 38.9 for the video run.
- The policy consistently drives the **right** leg harder. That fits a robot whose constant-speed runs all veer **left**.
- Baseline percent from the 3 policy logs, using the checklist formula: **40 %**.

**Not done:** the optional steps O1–O5 (speed under load, lost-connection test, 100 % drift tests, hand tests).

## Julian's measurements

All in mm, measured with a ruler. Body sizes are for the plastic body only.

| What | Model | Measured |
|---|---|---|
| Weight of the whole robot | | **96 g** |
| Body length, front to back | ~80 | 80 |
| Body width, left to right | ~48 | 48 |
| Body height | ~30 | 30 |
| Axle height above the floor, legs at 0° | 15.0 | 15 |
| Front of the body to the axle | | 16 |
| Hub diameter, right / left | 25 / 25 | 25 / 25 |
| Hub sticks out from the body side, right / left | ~8 / ~8 | 8 / 8 |
| Right leg: axle hole / total holes | short arm 16, long arm 48 | 2 / 7 |
| Left leg: axle hole / total holes | short arm 16, long arm 48 | 2 / 7 (identical to the right) |
| Leg length, tip to tip | 64 | 63 |
| Leg thickness | ~8 | 8 |

Hole 2 of 7 on a 1×8 Technic brick is 16 mm from the end, so the CAD's 16 / 48 mm arms are right.

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
4. **Every constant-speed run turned left** (47–170°). The policy runs ended between 13° right and 12° left.
5. **Hand turn estimates matched the hub's yaw** to within 1–4° on every run with both. This confirms the IMU calibration (YAW_SIGN, ANGLE_UNIT_DEG = 0.1).
