# FakeRobot check: does the robot-side code reproduce the evaluation?

- 100 random lopsided FakeRobots (seeds 0-99), 20 s each, driven through `robot/run_policy.py` (hub units, `units.py`, Bluetooth delay, whole percents).
- Policy: `train/logs/rsl_rl/walk_straight_v2/2026-11-13_18-36-30_v2/model_799.pt`. Physics: `robot/model/scene.xml` (the training model, elliptic friction, checked field by field against MJLab).
- Baseline: both legs at a constant 63 rpm (the policy's average command).
- evaluate.py columns: from `docs/eval_results_v2_dt0.002.md` (MJLab, 100 robots, seed 7). The robots are drawn from the same ranges but are not the same 100, so expect similar statistics, not identical numbers. v2: evaluate.py draws each robot's top speed from 80-140 rpm; here the robot side fixes it at config.POLICY_TOP_RPM = 110 rpm.
- Leg speed input: v2 trained on the encoder average (the 'encoder' column is the real set-up); the 'hub speed' column is the instantaneous speed, which v2 never saw.
- Values: mean / median / worst 5 % of the absolute value (forward: mean / median / lowest 5 %).

| Measure | Baseline: evaluate.py | Baseline: FakeRobot | Policy: evaluate.py | Policy: FakeRobot, encoder speed | Policy: FakeRobot, hub speed |
|---|---|---|---|---|---|
| Sideways drift (mm) | 566 / 551 / 1222 | 523 / 474 / 1174 | 101 / 74 / 237 | 101 / 91 / 235 | 94 / 78 / 224 |
| Heading error (deg) | 94 / 95 / 163 | 82 / 71 / 165 | 7 / 6 / 18 | 8 / 6 / 17 | 9 / 6 / 16 |
| Forward distance (mm) | 392 / 338 / -462 | 457 / 424 / -443 | 1609 / 1587 / 1033 | 1538 / 1530 / 1076 | 1526 / 1526 / 989 |
| Flipped | 0 of 100 | 0 of 100 | 0 of 100 | 1 of 100 | 1 of 100 |
| Decisions with a command clipped at 100 % | - | 0 | - | 0 | 0 |
