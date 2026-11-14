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
   - `robot/model/policy_meta.json` must say which policy is loaded (`checkpoint`, `training_round`). The v2 policy (`walk_straight_v2/.../model_799.pt`) is exported.
   - v2 outputs a **fraction of the top speed**. `config.POLICY_TOP_RPM` (110 rpm, inside the trained 80–140 rpm) sets what a full action means. The laptop turns every action into an rpm at or below that, and only then into a percent, so the legs never go faster than in training. With the ~330 rpm motor, a full action is only about 33%.
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
| 3 | On the stand | `robot/calibration/measure_rpm.py` | Nothing: it runs 25 / 50 / 75 / 100% for 4 s each | `RPM_AT_PERCENT`, `RPM_MEASURED = True` (replaces the placeholder from the published specs, 334 rpm at 100%). **Read the speed check:** it says what percent a full action becomes. It warns only if the motor cannot reach `POLICY_TOP_RPM` |
| 3b | On the table (optional) | `robot/calibration/measure_rpm.py --on-table` | Let it walk about 1 m | Nothing; write down the speed under load. If it is much lower than on the stand at the same percent, the hub does **not** hold the speed (the "PWM" case in `docs/spec_motor_check.md`) |
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
   - Command: `robot/calibration/drift_test.py --legs in --percent 35`
   - Put the robot on the start line, with both legs at 0°. It runs 10 s at 35% (about the policy's top speed).
   - **Not 100% first.** With the motor's published specs (~334 rpm), the simulated robot flips within about half a second at 100% (`docs/hand_tests_sim_spec_*_100.md`). Try 100% only after 35% worked, with a hand ready to catch it.
   - Then measure and type in:
     - the straight-line distance from start to end (mm)
     - the sideways offset from the line (+ = right)
     - the turn angle from the video (+ = left)
9. **Same, legs out of step.**
   - Command: `robot/calibration/drift_test.py --legs out --percent 35`
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
13. Simulator side, with the measured rpm table already in `config.py` and the measured weight:
    - `robot/sim_hand_tests.py --motor regulated --percent 35 --body-mass-kg <motor weight in kg> --tag real_35` (use `--motor pwm` if step 3b showed the speed sagging under load)
    - `robot/compare_drift.py --sim docs/data/hand_tests_sim_heading_real_35.csv --real docs/data/<drift_in>.csv docs/data/<drift_out>.csv`

    This produces the real-vs-sim tables and plots.
14. Fill in Julian's column in `docs/hand_tests_sim.md`, and write the results into `docs/process_log.md`.
