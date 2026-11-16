"""
LEGO-looking parts for PICTURES ONLY (Notion cover, slides). Nothing here is used by the
simulation: cad/robot.xml, sim/, train/ and robot/ do not read this folder.

Downloads two LDraw parts with every subpart and primitive they use, and converts them to
binary STL in MILLIMETRES (1 LDU = 0.4 mm), placed in OUR ROBOT'S axes so they line up with
cad/robot.xml without any rotating in Onshape:
    x = robot's RIGHT, y = robot's FRONT (walking direction), z = UP

  double_motor.stl              118091p01, Electric Bluetooth Double Motor (unofficial part,
                                Philippe Hurbain, CC BY 4.0). Origin = the middle of the motor
                                axle (halfway between the two hub centres), axle along x.
  double_motor_<colour>.stl     the same motor split by LDraw colour, so each piece can get its
                                own appearance in Onshape (body, bottom, hubs, prints)
  technic_brick_1x8_leg.stl     3702, Technic Brick 1 x 8 with Holes (official part, James
                                Jessiman, CC BY 4.0), laid out as a LEG at angle 0: origin =
                                the centre of the 2nd hole (the pivot), hole axis along x, long
                                arm pointing forward (+y), studs up, centred on x = 0

How it works:
  1. Fetch the part file from library.ldraw.org, then every file it references (line type 1),
     recursively: unofficial library first (the motor is unofficial), then the official one;
     sub-parts live in parts/s/, primitives in p/ (and p/48/, p/8/ for high/low resolution).
     Downloads are cached in --cache (default: a folder next to this script, not in git).
  2. Flatten: every reference is "colour x y z a b c d e f g h i file" = a 3x3 matrix and an
     offset; triangles (type 3) and quads (type 4, split in two) are transformed into the
     part's frame. Lines (types 2 and 5) are drawing edges, not surfaces: skipped.
     Colour 16 means "the colour of the parent reference" and is inherited down.
  3. Face orientation (LDraw "BFC"): each file says CCW or CW; "0 BFC INVERTNEXT" and a
     mirroring matrix (negative determinant) flip the next reference. Triangles are written
     counter-clockwise seen from outside, so the normals point out (checked: the enclosed
     volume comes out positive).
  4. LDraw axes (y points DOWN) -> robot axes, millimetres:  x_r = -x, y_r = -z, z_r = -y
     (a proper rotation, so nothing is mirrored), then shifted to the origin described above.

Run from the HW8 folder (downloads ~100 small files the first time):
  ../../.venv/bin/python cad/visual/ldraw_to_stl.py
"""

import argparse
import shutil
import ssl
import struct
import subprocess
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = "https://library.ldraw.org/library"
LDU_MM = 0.4
# LDraw (x right, y DOWN, z toward the viewer) -> robot (x right, y front, z up), in mm.
# The motor's axle sits toward LDraw -z of its body, and our robot's front is the axle end.
TO_ROBOT = np.array([[-1, 0, 0], [0, 0, -1], [0, -1, 0]], dtype=float) * LDU_MM
assert abs(np.linalg.det(TO_ROBOT / LDU_MM) - 1) < 1e-9          # a rotation: no mirroring
# LDraw colour codes (official LDConfig.ldr) -> file name. 16 = "main colour": the colour the
# part is placed with (the real 45622 motor body is white).
COLOUR_NAMES = {16: "main", 41: "trans_medium_blue", 0: "black", 3: "dark_turquoise", 7: "light_grey", 15: "white", 71: "light_bluish_grey",
                72: "dark_bluish_grey", 4: "red", 14: "yellow", 1: "blue", 2: "green", 25: "orange",
                26: "magenta", 19: "tan", 80: "metallic_silver"}


# ---------------------------------------------------------------- download
class NotHere(Exception):
    """The library has no file at this URL (HTTP 404): try the next place."""


def fetch(url: str) -> bytes:
    """Download one file, politely: certificate checking ON, a short pause before every
    download, and on "too many requests" (HTTP 429) wait and try again instead of giving up.
    Python from python.org on a Mac has no certificates until "Install Certificates.command"
    is run, so certifi's bundle is used when installed; curl (system certificates) otherwise."""
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    for attempt in range(6):
        time.sleep(0.5)                                     # be kind to library.ldraw.org
        req = urllib.request.Request(url, headers={"User-Agent": "ldraw-to-stl/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotHere(url) from None
            if e.code == 429:                               # rate limited: wait, then retry
                wait = int(e.headers.get("Retry-After") or 0) or 15 * (attempt + 1)
                print(f"  (the LDraw library asks to slow down: waiting {wait} s)", flush=True)
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if not shutil.which("curl"):
                raise
            res = subprocess.run(["curl", "-sL", "--max-time", "30", "-w", "%{http_code}", url],
                                 capture_output=True)
            body, code = res.stdout[:-3], res.stdout[-3:].decode(errors="replace")
            if code == "404":
                raise NotHere(url) from None
            if code == "429":
                time.sleep(15 * (attempt + 1))
                continue
            if code == "200":
                return body
            raise urllib.error.URLError(f"curl: HTTP {code}") from None
    raise RuntimeError(f"gave up on {url} after repeated 'too many requests'")


class Library:
    """Finds and caches LDraw files by the name used in a reference line."""

    def __init__(self, cache: Path):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.sources = {}                    # file name -> URL it came from

    def candidates(self, name: str):
        n = name.replace("\\", "/").lower()
        for lib in ("unofficial", "official"):
            if n.startswith("s/"):
                yield f"{BASE}/{lib}/parts/{n}"
            elif n.startswith(("48/", "8/")):
                yield f"{BASE}/{lib}/p/{n}"
            else:
                yield f"{BASE}/{lib}/parts/{n}"
                yield f"{BASE}/{lib}/p/{n}"

    def get(self, name: str) -> list[str]:
        key = name.replace("\\", "/").lower()
        path = self.cache / key.replace("/", "__")
        if not path.exists():
            for url in self.candidates(name):
                try:
                    data = fetch(url)
                except NotHere:
                    continue                                     # try the next place
                if data.lstrip().startswith(b"0"):               # an LDraw file, not an error page
                    path.write_bytes(data)
                    (self.cache / (path.name + ".url")).write_text(url)
                    break
            else:
                raise FileNotFoundError(f"{name} not found in the LDraw library")
        self.sources[key] = (self.cache / (path.name + ".url")).read_text()
        return path.read_text(encoding="utf-8", errors="replace").splitlines()


# ---------------------------------------------------------------- flatten to triangles
def flatten(lib: Library, name: str, M=np.eye(3), t=np.zeros(3), colour=16, invert=False, out=None):
    """All triangles of `name` in the top part's frame (LDU), as (colour, 3x3 vertices),
    counter-clockwise seen from outside."""
    out = [] if out is None else out
    ccw = True                                # the file's winding (BFC CERTIFY CCW / CW)
    invert_next = False
    for line in lib.get(name):
        tok = line.split()
        if not tok:
            continue
        kind = tok[0]
        if kind == "0":
            words = [w.upper() for w in tok[1:]]
            if words[:1] == ["BFC"]:
                if "CW" in words:
                    ccw = False
                if "CCW" in words:
                    ccw = True
                if "INVERTNEXT" in words:
                    invert_next = True
            continue
        c = int(tok[1]) if len(tok) > 1 and tok[1].lstrip("-").isdigit() else 16
        c = colour if c == 16 else c
        if kind == "1":
            v = [float(x) for x in tok[2:14]]
            t2 = np.array(v[:3])
            M2 = np.array(v[3:12]).reshape(3, 3)
            child_invert = invert ^ invert_next ^ (np.linalg.det(M2) < 0)
            flatten(lib, " ".join(tok[14:]), M @ M2, M @ t2 + t, c, child_invert, out)
            invert_next = False
        elif kind in ("3", "4"):
            n = 3 if kind == "3" else 4
            p = np.array([float(x) for x in tok[2:2 + 3 * n]]).reshape(n, 3) @ M.T + t
            tris = [p[[0, 1, 2]]] if n == 3 else [p[[0, 1, 2]], p[[0, 2, 3]]]
            flip = (not ccw) ^ invert
            for tri in tris:
                out.append((c, tri[[0, 2, 1]] if flip else tri))
    return out


# ---------------------------------------------------------------- STL
def write_stl(path: Path, tris: np.ndarray, title: str):
    """Binary STL; tris: (n, 3, 3) in mm."""
    with open(path, "wb") as f:
        f.write(title.encode()[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            n = np.cross(b - a, c - a)
            n = n / (np.linalg.norm(n) or 1.0)
            f.write(struct.pack("<12fH", *n, *a, *b, *c, 0))


def volume(tris: np.ndarray) -> float:
    """Signed enclosed volume (mm^3); positive when the normals point outward."""
    return float(np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum() / 6)


def to_robot(tris_ldu: np.ndarray, origin_ldu: np.ndarray) -> np.ndarray:
    return (tris_ldu - origin_ldu) @ TO_ROBOT.T


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--cache", type=Path, default=HERE / "ldraw_cache")
    a = ap.parse_args()
    lib = Library(a.cache)

    # ---- motor: origin halfway between the two hub centres (their reference points)
    motor_lines = lib.get("118091p01.dat")
    hubs = [np.array([float(x) for x in l.split()[2:5]]) for l in motor_lines      # noqa: E741
            if l.startswith("1 ") and l.split()[-1].lower().startswith("5319")]
    assert len(hubs) == 2, hubs
    axle_mid = (hubs[0] + hubs[1]) / 2
    raw = flatten(lib, "118091p01.dat")
    tris = to_robot(np.array([t for _, t in raw]), axle_mid)
    write_stl(HERE / "double_motor.stl", tris, "LDraw 118091p01 Double Motor, mm, robot axes")
    by_colour = defaultdict(list)
    for (c, _), tri in zip(raw, tris):
        by_colour[c].append(tri)
    for c, ts in sorted(by_colour.items()):
        write_stl(HERE / f"double_motor_{COLOUR_NAMES.get(c, f'colour{c}')}.stl", np.array(ts),
                  f"LDraw 118091p01 colour {c}, mm, robot axes")
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    print(f"double_motor.stl: {len(tris)} triangles, size {hi - lo} mm, volume {volume(tris) / 1000:.1f} cm^3")
    print(f"  colours: " + ", ".join(f"{COLOUR_NAMES.get(c, c)} ({len(v)} triangles)" for c, v in sorted(by_colour.items())))
    # where the hubs end along the axle (to place the legs)
    hub_tris = []
    for line in motor_lines:
        if line.startswith("1 ") and line.split()[-1].lower().startswith("5319"):
            v = [float(x) for x in line.split()[2:14]]
            sub = flatten(lib, line.split()[-1], np.array(v[3:12]).reshape(3, 3), np.array(v[:3]))
            hub_tris.append(to_robot(np.array([t for _, t in sub]), axle_mid).reshape(-1, 3))
    for h in hub_tris:
        print(f"  hub: x {h[:, 0].min():+.1f} .. {h[:, 0].max():+.1f} mm, y {h[:, 1].min():+.1f} .. "
              f"{h[:, 1].max():+.1f}, z {h[:, 2].min():+.1f} .. {h[:, 2].max():+.1f}")

    # ---- leg: Technic brick 1x8, origin at its 2nd hole, laid out as our leg at angle 0
    # brick: long along LDraw x, holes along LDraw z at x = -60..60 (step 20), 10 LDU below the top
    raw = flatten(lib, "3702.dat")
    pivot = np.array([-40.0, 10.0, 0.0])                     # 2nd hole from the -x end
    tris = np.array([t for _, t in raw]) - pivot
    # brick -> leg: long axis -> +y (the long arm, from hole 2 to the far end, points forward),
    # hole axis -> x, up stays up. As a rotation (no mirroring): x_r = -z, y_r = x, z_r = -y
    B = np.array([[0, 0, -1], [1, 0, 0], [0, -1, 0]], dtype=float)
    assert abs(np.linalg.det(B) - 1) < 1e-9
    tris = tris @ (B * LDU_MM).T
    write_stl(HERE / "technic_brick_1x8_leg.stl", tris, "LDraw 3702 Technic brick 1x8, mm, leg at angle 0")
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    print(f"technic_brick_1x8_leg.stl: {len(tris)} triangles, x {lo[0]:+.1f}..{hi[0]:+.1f}, "
          f"y {lo[1]:+.1f}..{hi[1]:+.1f}, z {lo[2]:+.1f}..{hi[2]:+.1f} mm, volume {volume(tris) / 1000:.2f} cm^3")
    (HERE / "ldraw_sources.txt").write_text(
        "Every LDraw file used, and where it was downloaded from (library.ldraw.org):\n"
        + "\n".join(f"{k}\t{v}" for k, v in sorted(lib.sources.items())) + "\n")
    print(f"{len(lib.sources)} LDraw files used; list in cad/visual/ldraw_sources.txt")


if __name__ == "__main__":
    main()
