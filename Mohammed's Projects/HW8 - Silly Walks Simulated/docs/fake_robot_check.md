# FakeRobot check: does the robot-side code reproduce the evaluation?

- 100 random lopsided FakeRobots (seeds 0-99), 20 s each, driven through `robot/run_policy.py` (hub units, `units.py`, Bluetooth delay, whole percents).
- Policy: `train/logs/rsl_rl/walk_straight/2026-11-12_22-50-21_first_check/model_299.pt`. Physics: `robot/model/scene.xml` (the training model, elliptic friction, checked field by field against MJLab).
- Baseline: both legs at a constant 65 rpm (the policy's average command).
- evaluate.py columns: from `docs/eval_results_dt0.002.md` (MJLab, 100 robots, seed 7). The robots are drawn from the same ranges but are not the same 100, so expect similar statistics, not identical numbers.
- Values: mean / median / worst 5 % of the absolute value (forward: mean / median / lowest 5 %).

| Measure | Baseline: evaluate.py | Baseline: FakeRobot | Policy: evaluate.py | Policy: FakeRobot, encoder speed | Policy: FakeRobot, hub speed |
|---|---|---|---|---|---|
| Sideways drift (mm) | 453 / 448 / 998 | 490 / 444 / 1093 | 67 / 58 / 148 | 72 / 64 / 141 | 58 / 55 / 127 |
| Heading error (deg) | 72 / 65 / 168 | 81 / 75 / 171 | 6 / 5 / 14 | 13 / 6 / 72 | 10 / 6 / 43 |
| Forward distance (mm) | 596 / 614 / -175 | 519 / 599 / -276 | 1144 / 1090 / 840 | 1044 / 1045 / 528 | 1057 / 1076 / 501 |
| Flipped | 0 of 100 | 2 of 100 | 0 of 100 | 6 of 100 | 9 of 100 |
| Decisions with a command clipped at 100 % | - | 0 | - | 0 | 0 |
