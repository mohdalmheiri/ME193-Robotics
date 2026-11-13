# Evaluation: baseline vs. trained policy (dt0.001)

- Checkpoint: `train/logs/rsl_rl/walk_straight/2026-11-12_22-50-21_first_check/model_299.pt`
- 100 randomly lopsided robots (seed 7), 20 s each, physics step 0.001 s, same robots for both drivers: yes
- Baseline: both legs at a constant 64 rpm (the policy's average command)

Values are mean / median / worst 5 % (95th percentile) of the absolute value at the end.

| Measure | Baseline (equal speeds) | Trained policy |
|---|---|---|
| Sideways drift (mm) | 447 / 432 / 932 | 86 / 75 / 188 |
| Heading error (deg) | 72 / 63 / 171 | 6 / 5 / 14 |
| Forward distance (mm) | 612 / 608 / -211 (worst 5 %) | 1343 / 1311 / 945 (worst 5 %) |
| Flipped | 0 of 100 | 0 of 100 |
