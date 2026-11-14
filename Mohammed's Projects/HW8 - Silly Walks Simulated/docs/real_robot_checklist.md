# Real-robot session checklist

Do these steps in this order. Every command runs from the HW8 folder (`Mohammed's Projects/HW8 - Silly Walks Simulated`) with the shared environment, `../../.venv/bin/python`.

After each calibration, **paste the printed lines into `robot/config.py`** before starting the next one. Each script needs the ones before it.

Any script can be rehearsed first with the simulator by adding `--fake`.

## Before the session (laptop, about 5 min)

1. **Battery and power.**
   - Charge the Double Motor.
   - Plug in the laptop.
   - Turn Bluetooth on.
2. **Policy.**
   - `robot/model/policy_meta.json` must say which policy is loaded (`checkpoint`, `training_round`). Use the v2 policy once it is exported.
3. **Tests**, about 3 min. All must say "checks passed":
   ```bash
   ../../.venv/bin/python robot/tests/test_units.py
   ../../.venv/bin/python robot/tests/test_policy.py
   ../../.venv/bin/python robot/tests/test_safety.py
   ../../.venv/bin/python robot/tests/test_real_robot_dryrun.py
   ../../.venv/bin/python robot/tests/test_calibration.py
   ```
4. **Set-up.**
   - A clear table or floor, at least 1.2 m × 1 m.
   - A straight tape line for the start direction.
   - A phone that can film from straight above.
   - Something to stand the robot on so the legs spin freely (a mug or a box).
   - A tape measure.

**Words used below:**
- **FRONT** = the end of the robot next to the motor axle. The body sticks out mostly *behind* the axle.
- **Legs at 0°** = pointing straight forward and flat, with the long arm (48 mm) in front of the axle.
- **Walking direction:** when a leg points down, its tip sweeps toward the robot's *back*, like a wheel rolling forward. The other direction flips the robot over.

## Calibration (about 15 min)

| # | Robot | Command | What you do | Paste |
|---|---|---|---|---|
| 1 | On the stand, legs free | `robot/calibration/motor_direction.py` | Watch each leg spin at 20%. Say which leg it was (r/l) and whether it turned the walking way (y/n) | `ROBOT_RIGHT_IS_LEGO`, `UPRIGHT_PERCENT_SIGN`, `ENCODER_SIGN` |
| 2 | On the table, motors off | `robot/calibration/leg_zero.py` | Turn both legs by hand to 0° and press Enter. Then turn the right leg so its long arm points straight up | `LEG_ZERO_DEG` (check the quarter-turn change reads about ±90°) |
| 3 | On the stand | `robot/calibration/measure_rpm.py` | Nothing: it runs 25 / 50 / 75 / 100% for 4 s each | `RPM_AT_PERCENT`, `RPM_MEASURED = True`. **Read the speed warning:** if 100% is outside the trained range, the policy should be retrained |
| 3b | On the table (optional) | `robot/calibration/measure_rpm.py --on-table` | Let it walk about 1 m | Nothing; write down the speed under load |
| 4 | On the table | `robot/calibration/imu_axes.py` | Flat → front down (lift the back about 45°) → right side down (lift the left side) → flat → turn a quarter turn to the LEFT | `BODY_FROM_HUB`, `ANGLE_UNIT_DEG`, `PITCH_SIGN`, `ROLL_SIGN`, `YAW_SIGN`, `GYRO_SIGN`, `PITCH_ROLL_SWAPPED`. It must print no warnings |

The script in step 3 also reports what the hub's "speed" number means. If it follows the measured speed, `LEG_SPEED_SOURCE = "hub_speed"` becomes possible. **v2 was trained with the encoder version, so keep `"encoder"`.**

## Safety checks (about 5 min, robot on the stand)

5. **Short dry run.**
   - Command: `robot/run_policy.py --real --seconds 5 --name standcheck`
   - Both legs should spin the walking way.
   - It should stop by itself after 5 s and save a CSV in `robot/runs/`.
6. **Ctrl-C.**
   - Start the same command, then press Ctrl-C after 2 s.
   - The motors must stop.
7. **Lost connection.**
   - Start the same command with `--seconds 15`.
   - After 3 s, switch off the laptop's Bluetooth.
   - **Do the legs stop by themselves?** Write the answer in the process log. The laptop cannot send a stop over a dead link, so this is the hub's own behaviour.

## Measurements to compare with the simulator (about 15 min, filmed from above)

8. **Fixed-speed drift test, legs in step.**
   - Command: `robot/calibration/drift_test.py --legs in`
   - Put the robot on the start line, with both legs at 0°. It runs 10 s at 100%.
   - Then measure and type in:
     - the straight-line distance from start to end (mm)
     - the sideways offset from the line (+ = right)
     - the turn angle from the video (+ = left)
9. **Same, legs out of step.**
   - Command: `robot/calibration/drift_test.py --legs out`
   - Right leg at 0°. Left leg a quarter turn ahead, long arm pointing straight up.
10. **Baseline runs** (3 runs, filmed, measured by hand like step 8).
    - Command: `robot/run_policy.py --real --constant 50 --seconds 20 --name baseline`
    - Use the percent the policy uses on average: the mean of `pct_r` / `pct_l` in a step-11 log. Run step 11 once first if needed.
11. **Policy runs** (3–5 runs, filmed, measured by hand).
    - Command: `robot/run_policy.py --real --seconds 20 --name policy`
    - Start each run on the line, facing along it.
    - Write the reason the run ended for each (it is printed): time limit / tipped over / ...

## Afterwards (laptop)

12. Copy the CSVs (and the drift test `.json` files) that the write-up cites from `robot/runs/` to `docs/data/`. `robot/runs/` itself is not committed.
13. Simulator side, using the measured top speed:
    - `robot/sim_hand_tests.py --rpm <measured rpm at 100%>`
    - `robot/compare_drift.py --real docs/data/<drift_in>.csv docs/data/<drift_out>.csv`

    This produces the real-vs-sim tables and plots.
14. Fill in Julian's column in `docs/hand_tests_sim.md`, and write the results into `docs/process_log.md`.
