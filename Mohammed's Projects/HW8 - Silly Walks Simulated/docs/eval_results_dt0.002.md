# Evaluation: baseline vs. trained policy (dt0.002)

- Checkpoint: `train/logs/rsl_rl/walk_straight/2026-11-12_22-50-21_first_check/model_299.pt`
- 100 randomly lopsided robots (seed 7), 20 s each, physics step 0.002 s, same robots for both drivers: yes
- Baseline: both legs at a constant 65 rpm (the policy's average command)

Values are mean / median / worst 5 % (95th percentile) of the absolute value at the end.

| Measure | Baseline (equal speeds) | Trained policy |
|---|---|---|
| Sideways drift (mm) | 453 / 448 / 998 | 67 / 58 / 148 |
| Heading error (deg) | 72 / 65 / 168 | 6 / 5 / 14 |
| Forward distance (mm) | 596 / 614 / -175 (worst 5 %) | 1144 / 1090 / 840 (worst 5 %) |
| Flipped | 0 of 100 | 0 of 100 |
