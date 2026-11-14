"""
Proof that the class demo (robot/demo_live.py) shows the SAME robot behaviour as the tested
control loop (robot/run_policy.py), not a look-alike.

How it works:
  1. For several robots (seeds), run the demo headless (both drivers, as fast as possible) and
     run_policy.run on a fresh FakeRobot with the same seed and driver. Compare the true end
     position, heading and every leg command: they must be EXACTLY equal (same physics steps,
     same decisions at the same times, same random draws). Robots that tip over are compared
     at the moment run_policy.run stopped (the demo keeps showing the fallen robot after).
  2. The demo's default robot (DEMO_SEED) must be a clear example, as the demo script says:
     baseline heading error > 45 deg, policy < 15 deg, nobody flips.
  3. The two-robot display model builds, has both robots, and copying a pose into it puts each
     robot on its own start line, facing up the screen.
  4. A 2 s video renders without a window (the backup video path).

Run from the HW8 folder:  ../../.venv/bin/python robot/tests/test_demo.py
"""

import math
import sys
import tempfile
from pathlib import Path

import numpy as np

ROBOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROBOT_DIR))
import demo_live as D  # noqa: E402
from fake_robot import FakeRobot  # noqa: E402
from policy import Policy  # noqa: E402
from run_policy import run  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ({detail})" if detail else ""))


SECONDS = 15.0
print("1. demo == run_policy.run, same robot and driver")
for seed in (D.DEMO_SEED, 3, 17, 60):
    walkers, base_pct = D.headless(seed, {}, SECONDS)
    c = D.baseline_action(seed, {}, SECONDS)
    for key, make in (("pol", Policy), ("base", lambda: (lambda obs: np.array([c, c])))):
        cmds = []
        inner = make()
        pol = lambda obs, inner=inner: cmds.append(a := inner(obs)) or a     # noqa: E731
        fr = FakeRobot(seed=seed)
        s = run(fr, SECONDS, None, policy=pol, quiet=True)
        w = walkers[key]
        if s["reason"].startswith("tipped"):
            ok = w.stopped and w.stopped.startswith("tipped") and w.k == s["decisions"]
            check(f"seed {seed} {key}: both stop at the same decision (tipped)", ok,
                  f"run_policy {s['decisions']}, demo {w.k}")
            continue
        t_run, t_demo = s["truth"], w.robot.truth()
        same = all(t_run[k] == t_demo[k] for k in ("side_mm", "fwd_mm", "heading_deg"))
        check(f"seed {seed} {key}: identical end state ({s['decisions']} vs {w.k} decisions)",
              same and s["decisions"] == w.k,
              f"heading {t_run['heading_deg']:+.2f} vs {t_demo['heading_deg']:+.2f} deg, "
              f"drift {t_run['side_mm']:+.1f} vs {t_demo['side_mm']:+.1f} mm")

print("2. the default demo robot is a clear example")
walkers, base_pct = D.headless(D.DEMO_SEED, {}, SECONDS)
hb = abs(walkers["base"].robot.truth()["heading_deg"])
hp = abs(walkers["pol"].robot.truth()["heading_deg"])
check("baseline heading error > 45 deg", hb > 45, f"{hb:.0f} deg")
check("policy heading error < 15 deg", hp < 15, f"{hp:.0f} deg")
check("nobody flips", walkers["base"].stopped == walkers["pol"].stopped == "finished",
      f"{walkers['base'].stopped} / {walkers['pol'].stopped}")

print("3. display model")
m, d, adr = D.display_model()
check("two robots in the display model", m.nbody == 2 + 2 * 3, f"{m.nbody} bodies")
walkers, _ = D.new_run(D.DEMO_SEED, {}, SECONDS)
ok = True
for key, x0 in (("base", -D.GAP_M / 2), ("pol", D.GAP_M / 2)):
    D.copy_pose(walkers[key], d, adr[key], x0)
    p = adr[key]["free"]
    q = d.qpos[p + 3:p + 7]
    yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
    ok &= abs(d.qpos[p] - x0) < 1e-9 and abs(d.qpos[p + 1]) < 1e-9 and abs(yaw) < 1e-6
check("each robot starts on its own start line, facing up the screen", ok)

print("4. backup video renders")
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "demo.mp4"
    D.record(type("A", (), {"seed": D.DEMO_SEED, "seconds": 2.0, "record": str(out)})(), {})
    check("2 s video written", out.exists() and out.stat().st_size > 10_000,
          f"{out.stat().st_size if out.exists() else 0} bytes")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
