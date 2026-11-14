"""
Proof that the one-command calibration (robot/calibrate.py) writes the RIGHT values into
config.py, safely, against fake hubs where every guess in config.py is wrong.

How it works, for each mis-wired fake hub in calibration/_fake_hubs.py (the same two hubs as
test_calibration.py: sensor turned 90 deg; sensor upside down):
  1. Copy robot/config.py to a temporary folder (the real config.py is never touched: its
     checksum is compared before and after the whole test).
  2. Run  calibrate.py --fake --fake-hub <hub> --config <the copy>  (all four steps, questions
     answered by the fake robot's oracle).
  3. Read the WRITTEN FILE on its own (not the program's memory) and compare every value with
     the hidden truth: wiring and signs exactly, leg zeros within 1.5 deg (including the fake
     encoder's own small calibration error, as in test_calibration.py), rpm at 100 % within 2 %.
  4. Safety: the backup equals the original file; every comment line of the original is still
     there; the file still imports; the walk test (the trained policy, 10 s, on 5 robots with this
     mis-wiring) works with the written config and does not with the original one.
     A motor slower than POLICY_TOP_RPM gets POLICY_TOP_RPM lowered to fit (inside 80-140 rpm).
  5. Rerun from step 4 only (--from imu_axes): only the imu values are rewritten, earlier
     values are kept, and the "measured by" notes are replaced, not stacked.
  6. A bad measurement is not written: a fake leg_zero whose quarter-turn check is wrong makes
     calibration stop at that step, with the file unchanged from the previous step.

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_calibrate.py
"""

import copy
import hashlib
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))
sys.path.insert(0, str(ROBOT_DIR / "calibration"))
import calibrate as K  # noqa: E402
import config as C  # noqa: E402
import leg_zero  # noqa: E402
from _fake_hubs import FAKE_HUBS  # noqa: E402
from fake_robot import HUB_KEYS, FakeRobot  # noqa: E402
from run_policy import run  # noqa: E402

REAL_CONFIG = ROBOT_DIR / "config.py"
DEFAULTS = {k: copy.deepcopy(getattr(C, k)) for k in HUB_KEYS + ("RPM_MEASURED", "POLICY_TOP_RPM")}
EXACT = ("ROBOT_RIGHT_IS_LEGO", "UPRIGHT_PERCENT_SIGN", "ENCODER_SIGN", "BODY_FROM_HUB",
         "ANGLE_UNIT_DEG", "PITCH_SIGN", "ROLL_SIGN", "YAW_SIGN", "GYRO_SIGN", "PITCH_ROLL_SWAPPED")
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ({detail})" if detail else ""))


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


def walk_test(values, truth) -> dict:
    """10 s of the trained policy on 5 robots with this mis-wiring (the symmetric one from
    test_calibration.py + 4 random lopsided ones) and these config values. One robot alone is
    too fragile a judge: e.g. the symmetric robot on the 95 rpm hub ends at -36 deg with
    POLICY_TOP_RPM 85 but -8 deg with 90 (docs/process_log.md, 2026-11-14 calibrate entry)."""
    K.apply_in_memory(values)
    out = []
    for seed, kw in ((5, {"randomize": False, "start_yaw": 0.3, "armature": 2e-4}), (5, {}), (6, {}), (7, {}), (8, {})):
        s = run(FakeRobot(seed=seed, hub=truth, **kw), 10.0, None, quiet=True)
        out.append({"reason": s["reason"], **s["truth"]})
    return {"flips": sum(o["reason"] != "time limit reached" for o in out),
            "heading_med": float(np.median([abs(o["heading_deg"]) for o in out])),
            "fwd_med": float(np.median([o["fwd_mm"] for o in out]))}


def walks(w):
    return w["flips"] == 0 and w["heading_med"] < 15 and w["fwd_med"] > 100


def wdesc(w):
    return f"{w['flips']}/5 flipped, median heading {w['heading_med']:.0f} deg, median forward {w['fwd_med']:.0f} mm"


def comments(text):
    return [l.strip() for l in text.splitlines() if l.strip().startswith("#")]   # noqa: E741


real_before = md5(REAL_CONFIG)
original = REAL_CONFIG.read_text()
for name, truth in FAKE_HUBS.items():
    print(f"\n=== Hidden hub: {name}")
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.py"
        shutil.copy2(REAL_CONFIG, cfg)
        res = K.main(["--fake", "--fake-hub", name, "--config", str(cfg)])
        check("calibration ran all four steps", res["stopped_at"] is None)
        got = K.load_file(cfg)                                  # the FILE, read on its own
        for k in EXACT:
            check(f"file has the true {k}", K.same(got[k], truth[k]), f"{K.fmt(got[k])} vs true {K.fmt(truth[k])}")
        # leg zero: what the encoder truly reads at leg-forward, incl. the fake's own encoder error
        calib = K.make_robot(True, truth, "leg_zero").leg_calib
        for leg in ("right", "left"):
            expect = (truth["LEG_ZERO_DEG"][leg] + truth["ENCODER_SIGN"][leg] * math.degrees(calib[leg])) % 360
            err = (got["LEG_ZERO_DEG"][leg] - expect + 180) % 360 - 180
            check(f"file has the {leg} leg's zero (within 1.5 deg)", abs(err) < 1.5,
                  f"{got['LEG_ZERO_DEG'][leg]:.1f} vs true {expect:.1f}")
        top, true_top = got["RPM_AT_PERCENT"][-1][1], truth["RPM_AT_PERCENT"][-1][1]
        check("file has the speed at 100 % (within 2 %)", abs(top - true_top) / true_top < 0.02,
              f"{top:.1f} vs true {true_top:.1f} rpm")
        check("RPM_MEASURED = True in the file", got["RPM_MEASURED"] is True)
        # a motor slower than POLICY_TOP_RPM (turned-90: 95 rpm < 110) -> top speed lowered,
        # still inside the trained range; a faster one (upside-down: 130 rpm) -> unchanged
        want_top = max(80.0, math.floor(0.9 * top)) if top < 0.97 * DEFAULTS["POLICY_TOP_RPM"] else DEFAULTS["POLICY_TOP_RPM"]
        check("POLICY_TOP_RPM fits the motor", got["POLICY_TOP_RPM"] == want_top and 80 <= got["POLICY_TOP_RPM"] <= 140,
              f"{got['POLICY_TOP_RPM']:.0f} rpm, motor {top:.0f} rpm")

        # safety
        check("backup equals the original config.py", res["backup"].read_text() == original)
        new_text = cfg.read_text()
        lost = [c for c in comments(original) if c not in comments(new_text)]
        check("every comment of the original is kept", not lost, f"lost: {lost[:2]}")
        check("one 'measured by' note per written value",
              new_text.count(K.MARK) == len(res["done"]), f"{new_text.count(K.MARK)} notes, {len(res['done'])} values")
        right = walk_test({k: got[k] for k in DEFAULTS}, truth)
        wrong = walk_test(DEFAULTS, truth)
        check("with the WRITTEN config the policy walks 5 robots with this wiring (no flips, median heading < 15 deg)", walks(right),
              wdesc(right))
        check("with the ORIGINAL config it does not", not walks(wrong),
              wdesc(wrong))

        # rerun from the last step only
        K.apply_in_memory(DEFAULTS)
        res2 = K.main(["--fake", "--fake-hub", name, "--config", str(cfg), "--from", "imu_axes"])
        got2 = K.load_file(cfg)
        check("--from imu_axes rewrites only the imu values",
              set(res2["done"]) == set(K.STEPS["imu_axes"][1]), sorted(res2["done"]))
        check("... and keeps the earlier steps' values",
              all(K.same(got2[k], got[k]) for k in ("ROBOT_RIGHT_IS_LEGO", "ENCODER_SIGN", "LEG_ZERO_DEG", "RPM_AT_PERCENT")))
        check("... with notes replaced, not stacked", cfg.read_text().count(K.MARK) == len(res["done"]))
        check("... and a second backup", len(list((Path(tmp) / "config_backups").glob("config_*.py"))) == 2)

        # a bad measurement is not written
        if name == "turned-90":
            shutil.copy2(REAL_CONFIG, cfg)
            K.apply_in_memory(DEFAULTS)
            good_oracle = leg_zero.fake_oracle
            # the "person" turns the right leg only ~40 deg instead of a quarter turn
            leg_zero.fake_oracle = lambda r: {**good_oracle(r), "right_up": lambda: r.pose_legs(0.7, 0.0)}
            try:
                res3 = K.main(["--fake", "--fake-hub", name, "--config", str(cfg)])
            finally:
                leg_zero.fake_oracle = good_oracle
            got3 = K.load_file(cfg)
            check("a failed leg_zero check stops calibration at leg_zero", res3["stopped_at"] == "leg_zero")
            check("... without writing LEG_ZERO_DEG", K.same(got3["LEG_ZERO_DEG"], DEFAULTS["LEG_ZERO_DEG"]))
            check("... while step 1's results are already saved",
                  K.same(got3["ENCODER_SIGN"], truth["ENCODER_SIGN"]))
    K.apply_in_memory(DEFAULTS)

check("the real robot/config.py was never touched", md5(REAL_CONFIG) == real_before)
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
