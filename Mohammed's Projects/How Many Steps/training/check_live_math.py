"""Check that the live step counter on the UNO Q (uno_q/python/step_counter.py)
does the same math as training (train_steps.py).

    python check_live_math.py          (from this folder)

1. The board's step_model.npz must be the same file as training's.
2. A few saved recordings (one per pace, plus zero-step trials) are fed
   through step_counter.LiveCounter in batches of 10 samples, as the board
   receives them. Every time it finishes a clip, the same 2 s of samples go
   through train_steps.clip_features and train_steps.numpy_predict, and the
   features and outputs must agree (to rounding: 1e-9 and 1e-6).
3. Trial totals, for comparison: the live count runs over the whole
   recording, while train_steps.py counts only the moving stretch (with its
   edge correction), so these agree closely but not exactly.
"""
import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import train_steps as ts  # noqa: E402

# Load the board's module by its path (it lives in the UNO Q app folder)
spec = importlib.util.spec_from_file_location("step_counter", ts.BOARD_MODEL.parent / "step_counter.py")
step_counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step_counter)

TRIALS = ["Mohammed_Walk_slow_T02", "Mohammed_Walk_normal_T05", "Mohammed_Walk_fast_T18",
          "Mohammed_Run_T19", "Mohammed_LegSwing_T03", "Mohammed_Stand_T01"]
BATCH = 10                      # the board pulls ~10 samples at a time
FEATURE_TOL, OUTPUT_TOL = 1e-9, 1e-6


def main():
    # 1. The same model file
    same_file = (HERE / "step_model.npz").read_bytes() == ts.BOARD_MODEL.read_bytes()
    print(f"Board's step_model.npz is the same file as training's: {'yes' if same_file else 'NO'}")
    model = np.load(HERE / "step_model.npz")
    committee = step_counter.Committee(ts.BOARD_MODEL)
    if committee.feature_set != ts.FEATURE_SET or committee.n_features != len(ts.feature_names(False)):
        sys.exit(f"Training uses FEATURE_SET={ts.FEATURE_SET!r}, the board's model {committee.feature_set!r}: "
                 "rerun train_steps.py")

    trials = {t["file"][:-4]: t for t in ts.good_trials()}
    worst_feature = worst_output = 0.0
    print(f"\n{'trial':24s} {'clips':>5s} {'features':>9s} {'outputs':>9s} | {'live, whole':>11s} "
          f"{'training, moving':>16s} {'true':>5s}")
    for name in TRIALS:
        tr = ts.load_trial(trials[name])
        ankle = tr["ankle"]

        # 2. Stream it through the live counter, remembering where each clip ended
        live = step_counter.LiveCounter(committee)
        ends, live_out = [], []
        for start in range(0, len(ankle), BATCH):
            for i in range(start, min(start + BATCH, len(ankle))):
                if live.add(ankle[i]):
                    ends.append(i + 1)
                    live_out.append((live.rate, live.speed))

        # ...and the same windows through training's functions
        feat_diff = out_diff = 0.0
        for end, (rate, speed) in zip(ends, live_out):
            window = ankle[end - ts.CLIP:end]
            f_train = ts.clip_features(window)
            f_live = step_counter.clip_features(window, committee.feature_set)
            feat_diff = max(feat_diff, float(np.abs(f_train - f_live).max()))
            out_train, _ = ts.numpy_predict(model, f_train[None, :])
            out_diff = max(out_diff, float(np.abs(out_train[0] - [rate, speed]).max()))
        worst_feature, worst_output = max(worst_feature, feat_diff), max(worst_output, out_diff)

        # 3. Totals: training's way (moving stretch, edge correction) with the full model
        X, _ = ts.trial_clips(tr, False)
        out, _ = ts.numpy_predict(model, X)
        train_total = float((out[:, 0] * ts.clip_seconds(tr)).sum())
        print(f"{name[9:]:24s} {len(ends):5d} {feat_diff:9.1e} {out_diff:9.1e} | {live.steps:11.1f} "
              f"{train_total:16.1f} {tr['steps']:5d}")

    ok = same_file and worst_feature < FEATURE_TOL and worst_output < OUTPUT_TOL
    print(f"\nLargest difference, features: {worst_feature:.1e}, outputs: {worst_output:.1e} -> "
          f"{'the live math matches training' if ok else 'MISMATCH'}")
    print("(Totals use the model trained on all trials, so they fit these trials closely; the fair test is "
          "results.md. The live count also counts the stomp and the standing before and after.)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
