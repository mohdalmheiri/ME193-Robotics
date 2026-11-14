# Evaluation: baseline vs. simple controller vs. trained policy (v2_dt0.002)

- Checkpoint: `train/logs/rsl_rl/walk_straight_v2/2026-11-13_18-36-30_v2/model_799.pt`
- 100 randomly lopsided robots (seed 7), 20 s each, physics step 0.002 s, same robots for all drivers: yes; training's random pushes OFF
- Baseline: both legs at a constant 58 % of each robot's top speed (80-140 rpm) (the policy's average command)
- Simple controller: right = c - K h, left = c + K h on the policy's own noisy heading input, same c; K tuned on 100 OTHER robots (seed 1)

Values are mean / median / worst 5 % (95th percentile) of the absolute value at the end.

| Measure | Baseline (equal speeds) | Simple controller (K = 32) | Trained policy |
|---|---|---|---|
| Sideways drift (mm) | 566 / 551 / 1222 | 59 / 49 / 137 | 101 / 74 / 237 |
| Heading error (deg) | 94 / 95 / 163 | 7 / 6 / 18 | 7 / 6 / 18 |
| Forward distance (mm) | 392 / 338 / -462 (worst 5 %) | 853 / 814 / 566 (worst 5 %) | 1609 / 1587 / 1033 (worst 5 %) |
| Flipped | 0 of 100 | 0 of 100 | 0 of 100 |

Gain tuning (seed 1; score = mean heading error + 10 deg per flip):

| K | Heading error, mean (deg) | Sideways drift, mean (mm) | Flipped | |
|---|---|---|---|---|
| 0.25 | 36.0 | 484 | 0 | |
| 0.5 | 19.4 | 293 | 0 | |
| 1 | 11.9 | 149 | 0 | |
| 2 | 11.8 | 101 | 0 | |
| 4 | 10.5 | 79 | 0 | |
| 8 | 7.5 | 65 | 0 | |
| 16 | 7.0 | 62 | 0 | |
| 32 | 6.8 | 57 | 0 | chosen |
