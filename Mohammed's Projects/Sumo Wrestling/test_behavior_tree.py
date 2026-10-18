"""Tests the behavior tree without any hardware.  Run:  python test_behavior_tree.py"""
import math
from behavior_tree import Inputs, SumoBrain


def inp(left=0, right=0, button=False, on_tape=False, color_ok=True, cm=None, age=math.inf):
    return Inputs(left, right, button, on_tape, color_ok, cm, age)


def check(name, d, left, right, branch):
    assert (d.left, d.right, d.branch) == (left, right, branch), f"{name}: got {d}"
    print(f"PASS  {name:45} -> {branch} ({left},{right})")


b = SumoBrain()
check("levers pass straight through", b.tick(inp(50, 40), 0.0), 50, 40, "DRIVE")
check("small lever wiggle is ignored", b.tick(inp(5, -5), 0.1), 0, 0, "DRIVE")

check("on tape: forward is blocked", b.tick(inp(80, 80, on_tape=True), 1.0), 0, 0, "EDGE")
check("on tape: backward still works", b.tick(inp(-60, -60, on_tape=True), 1.05), -60, -60, "EDGE")
check("on tape: pivot keeps backward wheel only", b.tick(inp(70, -70, on_tape=True), 1.1), 0, -70, "EDGE")
check("just left tape: still blocked briefly", b.tick(inp(80, 80), 1.2), 0, 0, "EDGE")
check("tape hold over: driving again", b.tick(inp(80, 80), 1.5), 80, 80, "DRIVE")

check("opponent close + charging = BOOST", b.tick(inp(60, 60, cm=20, age=0.1), 2.0), 100, 100, "BOOST")
check("opponent close but reversing = no boost", b.tick(inp(-60, -60, cm=20, age=0.1), 2.1), -60, -60, "DRIVE")
check("opponent far = no boost", b.tick(inp(60, 60, cm=90, age=0.1), 2.2), 60, 60, "DRIVE")
check("stale reading is ignored", b.tick(inp(60, 60, cm=20, age=0.5), 2.3), 60, 60, "DRIVE")
check("edge + opponent close = EDGE_PUSH", b.tick(inp(60, 60, on_tape=True, cm=20, age=0.1), 3.0), 100, 100, "EDGE_PUSH")
check("edge + opponent far = EDGE", b.tick(inp(60, 60, on_tape=True, cm=90, age=0.1), 3.5), 0, 0, "EDGE")
check("edge + stale reading = EDGE", b.tick(inp(60, 60, on_tape=True, cm=20, age=0.5), 4.0), 0, 0, "EDGE")

check("color sensor lost = stop", b.tick(inp(60, 60, color_ok=False), 5.0), 0, 0, "NO_EDGE")

d = b.tick(inp(60, 60, button=True), 6.0)
check("button press = OUT", d, 0, 0, "OUT"); assert d.play_sad_song
d = b.tick(inp(60, 60, button=True), 6.1)
check("holding the button: still OUT, song once", d, 0, 0, "OUT"); assert not d.play_sad_song
check("levers do nothing while OUT", b.tick(inp(100, 100), 6.2), 0, 0, "OUT")
check("press again = reset for next round", b.tick(inp(30, 30, button=True), 7.0), 30, 30, "DRIVE")
print("\nAll tests passed!")
