"""
One-command calibration: runs the four calibration scripts in order, asks their questions,
and WRITES the results into robot/config.py itself (after saving a backup), instead of
copy-pasting the printed lines.

  Run from the HW8 folder:
      ../../.venv/bin/python robot/calibrate.py                    the real Double Motor
      ../../.venv/bin/python robot/calibrate.py --fake             rehearsal, simulator, a hub
                                                                   wired as config.py says
      ../../.venv/bin/python robot/calibrate.py --fake --fake-hub upside-down
                                                                   rehearsal against a WRONGLY
                                                                   wired fake hub (turned-90 /
                                                                   upside-down, calibration/_fake_hubs.py)
  Options:
      --from leg_zero     start at this step (earlier results already in config.py are kept)
      --config PATH       write a different file (the tests use a temporary copy)

Steps (each one is the existing script's measure() function, so the questions, checks and
maths are exactly those of the separate scripts):
  1. motor_direction   robot on the STAND, legs free  -> ROBOT_RIGHT_IS_LEGO, UPRIGHT_PERCENT_SIGN,
                                                         ENCODER_SIGN
  2. leg_zero          robot on the TABLE, motors off -> LEG_ZERO_DEG
  3. measure_rpm       robot on the STAND, legs free  -> RPM_AT_PERCENT, RPM_MEASURED = True
  4. imu_axes          robot on the TABLE, motors off -> BODY_FROM_HUB, ANGLE_UNIT_DEG, PITCH_SIGN,
                                                         ROLL_SIGN, YAW_SIGN, GYRO_SIGN, PITCH_ROLL_SWAPPED

How config.py is changed (safely):
  - Before anything else, the whole file is copied to robot/config_backups/config_<date-time>.py
    (ignored by git). To undo:  cp robot/config_backups/config_<...>.py robot/config.py
  - After EACH step, only that step's assignment lines are replaced (found with Python's own
    parser, so multi-line values are handled). Every comment is kept; the comment after the
    value stays, and a line "# measured by calibrate.py on <date> (was: <old value>)" is put
    above it (replaced, not repeated, on a later run).
  - The new text is checked before it is saved: it must run as Python and give back exactly
    the measured values; otherwise nothing is written. The file is replaced in one go
    (write to a temporary file, then rename), so it is never half-written.
  - Each step's results are also put into the running program's config, so the next step
    already uses them (leg_zero needs the motor wiring, measure_rpm the walking direction).
  - If a step WARNS (e.g. the quarter-turn check is off, the motor cannot reach
    POLICY_TOP_RPM, the motion sensor never matched), it asks whether to keep the result
    (fake robot: not kept, and calibration stops), so a bad measurement is never written silently.
At the end: a table of every value (before -> after), what percent a full action now becomes,
and a SUGGESTED baseline percent (the policy's average command on 10 simulated robots with
the new config; confirm with the real policy runs' logs).
"""

import argparse
import ast
import math
import importlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROBOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROBOT_DIR))
sys.path.insert(0, str(ROBOT_DIR / "calibration"))
import config as C  # noqa: E402
import units as U  # noqa: E402
import imu_axes, leg_zero, measure_rpm, motor_direction  # noqa: E402,E401
from _common import FRONT_WORDS, Ask  # noqa: E402
from _fake_hubs import FAKE_HUBS  # noqa: E402

MARK = "# measured by calibrate.py on"
STEPS = {  # name: (where the robot goes, the config names it sets)
    "motor_direction": ("Put the robot on the STAND (or hold it up): both legs must spin freely.",
                        ("ROBOT_RIGHT_IS_LEGO", "UPRIGHT_PERCENT_SIGN", "ENCODER_SIGN")),
    "leg_zero": ("Put the robot on the TABLE (or hold it). Motors stay off.",
                 ("LEG_ZERO_DEG",)),
    "measure_rpm": ("Put the robot back on the STAND, legs free. It runs 25/50/75/100 % for "
                    "4 s each (16 s).", ("RPM_AT_PERCENT", "RPM_MEASURED")),
    "imu_axes": ("Put the robot FLAT on the TABLE. Motors stay off. You will hold it in 4 poses.",
                 ("BODY_FROM_HUB", "ANGLE_UNIT_DEG", "PITCH_SIGN", "ROLL_SIGN", "YAW_SIGN",
                  "GYRO_SIGN", "PITCH_ROLL_SWAPPED")),
}
ON_STAND = ("motor_direction", "measure_rpm")


# ---------------------------------------------------------------- values -> Python text
def plain(v):
    """numpy numbers -> plain Python numbers (so the file shows 83.5, not np.float64(83.5))."""
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(plain(x) for x in v)
    return v


def fmt(v) -> str:
    """A value as Python text in config.py's style (double quotes, signs written as +1/-1)."""
    if isinstance(v, bool):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, int):
        return f"{v:+d}" if v in (-1, 1) else str(v)
    if isinstance(v, float):
        return repr(round(v, 2))
    if isinstance(v, dict):
        return "{" + ", ".join(f"{fmt(k)}: {fmt(x)}" for k, x in v.items()) + "}"
    if isinstance(v, tuple):
        return "(" + ", ".join(fmt(x) for x in v) + ")"
    if isinstance(v, list):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    raise TypeError(f"cannot write {type(v)}")


def same(a, b) -> bool:
    """Equal as config values (tuples and lists count as equal; floats to 0.01)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.01
    return a == b


def load_file(path: Path) -> dict:
    """Run a config file on its own and return its top-level values."""
    ns = {}
    exec(compile(path.read_text(), str(path), "exec"), ns)
    return ns


def write_values(path: Path, values: dict, when: str):
    """Replace these assignments in the config file, keeping all comments (see the top)."""
    src = path.read_text()
    lines = src.splitlines(keepends=True)
    spans = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            old = " ".join(ast.get_source_segment(src, node.value).split())   # old value, one line
            spans[node.targets[0].id] = (node.lineno, node.end_lineno, node.end_col_offset, old)
    missing = set(values) - set(spans)
    if missing:
        raise KeyError(f"{path.name} has no line for {sorted(missing)}")
    for name in sorted(values, key=lambda k: -spans[k][0]):        # bottom-up: line numbers stay valid
        first, last, end_col, old_value = spans[name]
        trailing = lines[last - 1][end_col:].rstrip("\n")           # e.g. '   # "right" or "left"'
        start = first - 1
        if start > 0 and lines[start - 1].startswith(MARK):          # an earlier calibrate.py note:
            start -= 1                                               # replace it, don't stack them
        lines[start:last] = [f"{MARK} {when} (was: {old_value})\n",
                             f"{name} = {fmt(values[name])}{trailing}\n"]
    text = "".join(lines)
    # check before saving: it must run, and give back exactly what was measured
    ns = {}
    exec(compile(text, str(path), "exec"), ns)
    bad = [k for k, v in values.items() if not same(ns[k], v)]
    if bad:
        raise ValueError(f"the new {path.name} would not give back {bad}; nothing written")
    tmp = path.with_suffix(".py.tmp")
    tmp.write_text(text)
    tmp.replace(path)                                               # all at once


def apply_in_memory(values: dict):
    """Use the new values from now on in this program (the next step needs them)."""
    for k, v in values.items():
        setattr(C, k, v)
    importlib.reload(U)                     # units.py rebuilds its axis matrix / rpm table


# ---------------------------------------------------------------- the robot for each step
def make_robot(fake: bool, hub: dict | None, step: str):
    if fake:
        from fake_robot import FakeRobot
        # the same fake as test_calibration.py (seed 4, symmetric, legs at 0, v2 motor inertia)
        r = FakeRobot(seed=4, randomize=False, start_q=[0.0, 0.0], start_yaw=0.0, armature=2e-4, hub=hub)
        if step in ON_STAND:
            r.on_stand()
        return r
    from real_robot import RealRobot
    return RealRobot()


def run_step(step: str, robot, fake: bool):
    """One calibration -> (values for config.py, warnings, proposed extra changes).
    A proposal is a setting the measurement shows must change (asked before writing)."""
    mod = {"motor_direction": motor_direction, "leg_zero": leg_zero,
           "measure_rpm": measure_rpm, "imu_axes": imu_axes}[step]
    ask = Ask(mod.fake_oracle(robot) if fake and hasattr(mod, "fake_oracle") else None)
    warn, propose = [], {}
    if step == "measure_rpm":
        table = measure_rpm.report(measure_rpm.measure(robot), paste=False)
        vals = {"RPM_AT_PERCENT": [(int(p), float(r)) for p, r in table], "RPM_MEASURED": True}
        top = table[-1][1]
        lo, hi = U.META.get("top_speed_rpm_range", (U.META["max_speed_rpm"],) * 2)
        if top < lo:
            warn.append(f"{top:.0f} rpm at 100 % is below the slowest top speed v2 trained with "
                        f"({lo:.0f} rpm): the policy cannot be used as is (retrain, see the log)")
        elif top < 0.97 * C.POLICY_TOP_RPM:
            # the motor is slower than the chosen top speed but inside the trained range: lower
            # the top speed to 90 % of what the motor reaches (headroom for load and a
            # weaker battery), never below the trained range
            new_top = float(max(lo, math.floor(0.9 * top)))
            propose["POLICY_TOP_RPM"] = (new_top, f"the motor reaches only {top:.0f} rpm at 100 %, "
                                         f"below POLICY_TOP_RPM = {C.POLICY_TOP_RPM:.0f}; lower it to "
                                         f"{new_top:.0f} (90 % of the motor's top, inside the trained "
                                         f"{lo:.0f}-{hi:.0f} rpm)")
        return vals, warn, propose
    res = mod.measure(robot, ask)
    vals = {k: res[k] for k in STEPS[step][1]}
    if step == "leg_zero":
        vals["LEG_ZERO_DEG"] = {s: round(float(v), 1) for s, v in vals["LEG_ZERO_DEG"].items()}
        q = res["quarter_turn_change_deg"]
        if abs(abs(q) - 90) > 15:
            warn.append(f"the quarter-turn check read {q:+.0f} deg, not about 90: were the legs "
                        "really straight forward, and was the right leg turned a quarter turn?")
    if step == "imu_axes":
        warn += res["warnings"]
    return plain(vals), warn, propose


def suggest_baseline(n=10, seconds=15.0):
    """The policy's average command on n simulated robots with the current config -> percent.
    (evaluate.py's baseline rule; confirm with the real policy runs' logs.)"""
    from fake_robot import FakeRobot
    from policy import Policy
    from run_policy import run
    acts = []
    pol = Policy()
    for seed in range(n):
        run(FakeRobot(seed=seed), seconds, None, quiet=True,
            policy=lambda obs: acts.append(np.clip(a := pol(obs), -1, 1)) or a)
    c = float(np.mean(acts))
    return abs(U.command(np.array([c, c]))[0]["right"])


# ---------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(description="Run all calibrations and write the results into config.py")
    p.add_argument("--fake", action="store_true", help="rehearse with the simulator")
    p.add_argument("--fake-hub", choices=sorted(FAKE_HUBS), default=None,
                   help="with --fake: a deliberately mis-wired fake hub")
    p.add_argument("--from", dest="start", choices=list(STEPS), default="motor_direction")
    p.add_argument("--config", type=Path, default=ROBOT_DIR / "config.py")
    a = p.parse_args(argv)
    if a.fake_hub and not a.fake:
        p.error("--fake-hub needs --fake")
    hub = FAKE_HUBS[a.fake_hub] if a.fake_hub else None
    path = a.config.resolve()
    when = datetime.now().strftime("%Y-%m-%d %H:%M")

    # backup first
    backups = path.parent / "config_backups"
    backups.mkdir(exist_ok=True)
    backup = backups / f"config_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')}.py"
    shutil.copy2(path, backup)
    print(f"Backup of {path.name}: {backup}\n  (to undo everything:  cp '{backup}' '{path}')\n")
    before = load_file(path)
    apply_in_memory({k: before[k] for keys in (v[1] for v in STEPS.values()) for k in keys + ("POLICY_TOP_RPM",)})
    print(FRONT_WORDS + "\n")

    names = list(STEPS)
    done = {}
    for i, step in enumerate(names[names.index(a.start):], start=names.index(a.start) + 1):
        where, keys = STEPS[step]
        print(f"=== Step {i}/4: {step}")
        if a.fake:
            print(where)
        else:
            Ask(None).enter(where)            # waits for Enter once the robot is in place
        robot = make_robot(a.fake, hub, step)
        vals, warn, propose = run_step(step, robot, a.fake)
        for k, (v, why) in propose.items():
            print(f"  NOTE: {why}")
            ok = a.fake or Ask(None)(f"Write {k} = {fmt(v)} too?", "propose") == "y"
            if ok:
                vals[k] = v
            else:
                warn.append(f"{k} not changed: {why}")
        for w in warn:
            print(f"  *** WARNING: {w}")
        if warn:
            keep = (not a.fake) and Ask(None)("Keep this step's result anyway?", "keep") == "y"
            if not keep:
                print(f"Not written. Calibration stopped at {step}; earlier steps are saved. "
                      f"Fix the cause and rerun with:  --from {step}")
                return {"done": done, "stopped_at": step, "backup": backup}
        write_values(path, vals, when)
        apply_in_memory(vals)
        done.update(vals)
        for k in vals:
            print(f"  wrote {k} = {fmt(vals[k])}")
        print()

    # summary
    print("=== Summary (config.py, before -> after)")
    for k, v in done.items():
        changed = "" if same(before[k], v) else "   <- changed"
        print(f"  {k:22s} {fmt(before[k])}  ->  {fmt(v)}{changed}")
    full = abs(U.command(np.ones(2))[0]["right"])
    print(f"\nA full policy action now = POLICY_TOP_RPM {C.POLICY_TOP_RPM:.0f} rpm = {full} % power.")
    base = suggest_baseline()
    print(f"Suggested baseline percent: {base} %  (the policy's average command on 10 simulated "
          "robots; confirm with the mean of pct_r / pct_l in the real policy runs' logs)")
    print(f"\nBackup: {backup}")
    return {"done": done, "stopped_at": None, "backup": backup, "baseline_pct": base}


if __name__ == "__main__":
    main()
