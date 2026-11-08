"""
capture.py - take labeled photos of hands showing 0-5 fingers, for training.

The external webcam hangs off the laptop screen, looking down at a red square
taped on the desk. You hold up fingers inside the square and press the
matching number key; the tool cuts the square out of the picture, shrinks it
to 128x128 pixels and saves it in data/<number>/.

Three ways to run it:

  python capture.py --list
      Finds every camera, shows one snapshot from each, and suggests which is
      the external webcam. Note its number.

  python capture.py --camera 1 --person mohammed
      Live preview. Line the box up with the red square, press c to save it,
      then press 0-5 to take photos. (Leave out --camera after the first time;
      the number saved with the box is used.)

  python capture.py --samples --person mohammed
      Makes ../media/hand_samples_mohammed.png: one photo per class side by side,
      for the README.

Keys in the preview window (click the window first so it gets the key presses):
  w a s d     move the box 5 pixels      (W A S D with Shift: 25 pixels)
  [ ]         shrink / grow the box       ({ } with Shift: faster)
  f           fit the box to the red square automatically
  c           save the box to crop_config.json
  0-5         save one photo of that class (hold the key: about 5 per second)
  q or Esc    quit

Class "0" is a fist OR an empty square (no hand): later the lock uses "0" as
the pause between code digits, so collect both kinds under 0.
"""
import argparse
import json
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import hand_crop as hc

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"                  # data/0 ... data/5 (kept out of Git, see .gitignore)
MEDIA_DIR = HERE.parent / "media"         # sample pictures for the README
CLASSES = [str(d) for d in range(6)]      # "0" .. "5"
TARGET_PER_CLASS = 80                     # goal per class, per person
SAVE_INTERVAL = 0.2                       # at most one photo every 0.2 s = 5 per second while a key is held
STEP_SMALL, STEP_BIG = 5, 25              # box move/resize steps in pixels
MAX_CAMERAS = 6                           # how many camera numbers --list tries (0..5)
WINDOW = "capture (click here, then use the keys)"

# Why 128 x 128 (hc.IMAGE_SIZE)?
#   * It is big enough that each finger is still clearly a separate shape:
#     the square fills ~300 pixels of the camera picture, so shrinking to 128
#     keeps fingers several pixels wide.
#   * It is small enough to keep the network fast: 128*128*3 = 49,152 numbers per
#     photo. The UNO Q has to run the network live on its small processor with
#     no graphics chip, so every extra pixel costs time.
#   * Training can still shrink the photos further (to 96 or 64) to test speed,
#     but it can never add back detail that was not saved. So 128 is the
#     "biggest we might need" size, not necessarily the final one.
#   * Photos are saved as PNG: no compression blur, so they match the raw
#     frames the UNO Q will see live. Each is only ~30 KB.


# ---- Finding the right camera ------------------------------------------------

def mac_camera_names():
    """Names of the cameras macOS knows about (empty list on other systems).

    OpenCV only numbers cameras (0, 1, 2...) and cannot tell us their names, so
    the names come from macOS's own hardware report. The numbers OpenCV uses
    are NOT guaranteed to be in the same order as this list, which is why
    --list also shows a picture from each number.
    """
    if platform.system() != "Darwin":
        return []
    try:
        out = subprocess.run(["system_profiler", "SPCameraDataType", "-json"],
                             capture_output=True, text=True, timeout=15).stdout
        return [c.get("_name", "?") for c in json.loads(out).get("SPCameraDataType", [])]
    except Exception:
        return []


def camera_kind(name):
    """Guess what kind of camera a name belongs to."""
    low = name.lower()
    if "facetime" in low or "built-in" in low:
        return "built-in laptop camera: NOT this one"
    if "iphone" in low or "ipad" in low:
        return "iPhone (Continuity Camera): NOT this one"
    return "probably the external USB webcam"


def red_mask(frame):
    """White where the picture is red (the tape), black elsewhere.

    HSV describes colors by hue (which color), saturation (how strong) and
    value (how bright). Red sits at both ends of the hue circle, so two hue
    ranges are combined. Saturation and brightness must be fairly high so
    skin and brown desk wood are not counted as red.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 100, 70), (10, 255, 255)) | cv2.inRange(hsv, (170, 100, 70), (180, 255, 255))
    kernel = np.ones((5, 5), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)    # fill small gaps in the tape


def find_red_box(frame):
    """A square box around the biggest red shape in the frame, or None if there isn't one."""
    h, w = frame.shape[:2]
    contours, _ = cv2.findContours(red_mask(frame), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(biggest)
    if bw * bh < 0.02 * w * h:            # too small to be the square: probably a red speck
        return None
    size = max(bw, bh)                     # square that covers the whole taped area
    cx, cy = x + bw // 2, y + bh // 2
    return hc.clamp_box(cx - size // 2, cy - size // 2, size, w, h)


def read_frame(cap, tries=15):
    """Read a frame, skipping the first few: cameras often send black frames while they wake up."""
    frame = None
    for _ in range(tries):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
            if f.mean() > 5:               # not (almost) completely black
                break
    return frame


def list_cameras():
    """Print and show every camera, and suggest the one that sees the red square."""
    names = mac_camera_names()
    if names:
        print("Cameras macOS knows about:")
        for n in names:
            print(f"  - {n}  ({camera_kind(n)})")
        if all("probably" not in camera_kind(n) for n in names):
            print("  !! No external webcam in this list. Is it plugged in? (Try another USB port or cable.)")
    print("\nTrying camera numbers 0 to", MAX_CAMERAS - 1, "(errors for missing numbers are normal)...")
    found = []
    for i in range(MAX_CAMERAS):
        cap = hc.open_camera(i)
        if not cap.isOpened():
            cap.release()
            continue
        frame = read_frame(cap)
        cap.release()
        if frame is None:
            print(f"  camera {i}: opened but sent no picture")
            continue
        h, w = frame.shape[:2]
        red = 100 * (red_mask(frame) > 0).mean()   # percent of the picture that is red
        found.append((i, frame, red))
        print(f"  camera {i}: {w}x{h}, {red:.1f}% red")

    if not found:
        print("\nNo camera sent a picture. On a Mac, check System Settings > Privacy & Security > Camera:"
              " the app you run this from (Terminal or VS Code) must be allowed.")
        return
    best = max(found, key=lambda f: f[2])
    if best[2] > 1.0:
        print(f"\nSuggestion: camera {best[0]} sees the most red (the taped square), so it is probably"
              f" the external webcam. Check the pictures to be sure.")
    else:
        print("\nNo camera sees much red. Check the pictures: the external webcam is the one looking down at the desk.")

    # One window with a labeled snapshot from each camera; the external one shows the desk from above.
    tiles = []
    for i, frame, red in found:
        t = cv2.resize(frame, (320, 240))
        cv2.rectangle(t, (0, 0), (320, 28), (0, 0, 0), -1)
        cv2.putText(t, f"camera {i}  ({red:.0f}% red)", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        tiles.append(t)
    cv2.imshow("cameras (press any key to close)", np.hstack(tiles))
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    print(f"\nNext: python capture.py --camera <number> --person <your name>")


# ---- Photos on disk ----------------------------------------------------------

def clean_person(name):
    """Make a name safe for file names: lowercase letters, digits and dashes only."""
    name = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    if not name:
        sys.exit("--person needs a name with at least one letter or digit.")
    return name


def count_photos(person):
    """How many photos each class has: {class: (this person's, everyone's)}."""
    counts = {}
    for c in CLASSES:
        folder = DATA_DIR / c
        counts[c] = (len(list(folder.glob(f"{person}_*.png"))), len(list(folder.glob("*.png"))))
    return counts


def save_photo(image, digit, person):
    """Save one 128x128 photo as data/<digit>/<person>_<digit>_<date-time-ms>.png."""
    now = datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}"   # milliseconds keep names unique at 5/s
    folder = DATA_DIR / digit
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{person}_{digit}_{stamp}.png"
    if not cv2.imwrite(str(path), image):
        raise OSError(f"could not write {path}")
    return path


# ---- Drawing the window ------------------------------------------------------

def draw_view(frame, box, saved, crop, counts, person, message, flash):
    """The camera picture with the box, plus a side panel: the saved image, counts and keys."""
    fh, fw = frame.shape[:2]
    panel_w, help_h = 300, 90
    canvas = np.full((max(fh + help_h, 560), fw + panel_w, 3), 30, np.uint8)   # dark gray background
    canvas[:fh, :fw] = frame

    # Box: green when it matches crop_config.json, orange when it has unsaved changes
    x, y, s = box
    color = (80, 200, 80) if saved else (0, 165, 255)
    cv2.rectangle(canvas, (x, y), (x + s, y + s), color, 2)
    cv2.putText(canvas, "box saved" if saved else "box NOT saved: press c", (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    # Side panel: exactly what gets saved, shown twice as big
    px = fw + 22
    cv2.putText(canvas, f"saved image ({hc.IMAGE_SIZE}x{hc.IMAGE_SIZE})", (px, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    big = cv2.resize(crop, (256, 256), interpolation=cv2.INTER_NEAREST)
    canvas[34:290, px:px + 256] = big
    if flash:                                  # white frame for a moment after each photo
        cv2.rectangle(canvas, (px - 3, 31), (px + 258, 292), (255, 255, 255), 3)

    # Counts per class, with a bar toward the target (green once reached)
    cv2.putText(canvas, f"photos ({person} / everyone)", (px, 318), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    for k, c in enumerate(CLASSES):
        mine, total = counts[c]
        yy = 344 + k * 30
        frac = min(1.0, mine / TARGET_PER_CLASS)
        bar_color = (80, 200, 80) if mine >= TARGET_PER_CLASS else (0, 165, 255)
        cv2.rectangle(canvas, (px + 30, yy - 14), (px + 30 + 150, yy + 2), (70, 70, 70), -1)
        cv2.rectangle(canvas, (px + 30, yy - 14), (px + 30 + int(150 * frac), yy + 2), bar_color, -1)
        cv2.putText(canvas, c, (px + 6, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(canvas, f"{mine}/{TARGET_PER_CLASS}  ({total})", (px + 186, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
    cv2.putText(canvas, "0 = fist OR empty square", (px, 344 + 6 * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    # Key help under the camera picture, and the latest message
    lines = ["w a s d: move box (Shift = faster)    [ ]: smaller / bigger ({ } faster)",
             "f: fit box to the red square    c: save box    q / Esc: quit",
             "0-5: save a photo (hold for ~5 per second)"]
    for k, line in enumerate(lines):
        cv2.putText(canvas, line, (10, fh + 22 + k * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    if message:
        cv2.putText(canvas, message, (10, canvas.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
    return canvas


# ---- The live capture tool ---------------------------------------------------

def capture(camera, person):
    cfg = hc.load_config()
    if camera is None:
        if cfg is None:
            sys.exit("Which camera? Run  python capture.py --list  first, then add --camera <number>.")
        camera = cfg["camera_index"]
        print(f"Using camera {camera} (saved in crop_config.json). Check the preview shows the desk from above.")

    cap = hc.open_camera(camera)
    frame = read_frame(cap) if cap.isOpened() else None
    if frame is None:
        sys.exit(f"Camera {camera} sent no picture. Run --list to check the number, and on a Mac allow camera"
                 " access for Terminal/VS Code in System Settings > Privacy & Security > Camera.")
    # The picture must be exactly 640x480 (see hand_crop.py for why). Stop otherwise.
    try:
        hc.check_frame_size(frame)
    except hc.FrameSizeError as e:
        cap.release()
        sys.exit(f"STOPPED: {e}")
    fh, fw = frame.shape[:2]

    # Start from the saved box if there is one, otherwise a box in the middle of the picture.
    # A box saved for another picture size is refused, not stretched to fit.
    saved_box = None
    if cfg:
        try:
            box = saved_box = hc.box_from_config(cfg)
        except hc.FrameSizeError as e:
            cap.release()
            sys.exit(f"STOPPED: {e}")
        if cfg["camera_index"] != camera:
            print(f"Note: the box was saved with camera {cfg['camera_index']}; now using {camera}."
                  " Camera numbers can change after plugging things in, so just check the preview.")
    else:
        s = int(fh * 0.6)
        box = hc.clamp_box((fw - s) // 2, (fh - s) // 2, s, fw, fh)

    counts = count_photos(person)
    last_save, flash_until = 0.0, 0.0
    message = "Line the box up with the red square, press c, then 0-5." if saved_box is None else "Ready: press 0-5."
    cv2.namedWindow(WINDOW)

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("The camera stopped sending pictures (unplugged?).")
            break
        # Check EVERY picture: the camera once switched from 640x480 to 640x360
        # partway through a session, which silently changed what the box cut out.
        try:
            hc.check_frame_size(frame)
        except hc.FrameSizeError as e:
            print(f"STOPPED partway through: {e}\nPhotos saved before this point are fine.")
            break
        crop = hc.crop_and_resize(frame, box)       # taken from the clean frame, before anything is drawn on it
        now = time.time()
        view = draw_view(frame.copy(), box, box == saved_box, crop, counts, person, message, now < flash_until)
        cv2.imshow(WINDOW, view)

        key = cv2.waitKey(1) & 0xFF                 # 255 means no key this time
        if key == 255:
            continue
        ch = chr(key)
        x, y, s = box

        if ch in CLASSES:
            if box != saved_box:
                message = "The box has unsaved changes: press c first, so every photo uses the saved box."
            elif now - last_save >= SAVE_INTERVAL:  # holding a key repeats it; this caps it at ~5 photos/s
                path = save_photo(crop, ch, person)
                last_save, flash_until = now, now + 0.15
                mine, total = counts[ch]
                counts[ch] = (mine + 1, total + 1)
                message = f"saved {ch}: {path.name}"
        elif ch in "wasdWASD":
            step = STEP_BIG if ch.isupper() else STEP_SMALL
            dx = {"a": -step, "d": step}.get(ch.lower(), 0)
            dy = {"w": -step, "s": step}.get(ch.lower(), 0)
            box = hc.clamp_box(x + dx, y + dy, s, fw, fh)
        elif ch in "[]{}":
            step = STEP_BIG if ch in "{}" else STEP_SMALL
            grow = step if ch in "]}" else -step
            # grow or shrink around the center, so the box doesn't drift
            box = hc.clamp_box(x - grow // 2, y - grow // 2, s + grow, fw, fh)
        elif ch == "f":
            found = find_red_box(frame)
            if found:
                box = found
                message = "Box fitted to the red square. Check it, adjust if needed, then press c."
            else:
                message = "Couldn't find the red square (lighting? not in view?). Move the box by hand."
        elif ch == "c":
            hc.save_config(camera, fw, fh, box)
            saved_box = box
            message = f"Box saved to crop_config.json: x={box[0]} y={box[1]} size={box[2]}"
        elif ch == "q" or key == 27:                # 27 is the Esc key
            break

    cap.release()
    cv2.destroyAllWindows()
    if box != saved_box:
        print("Note: the last box changes were NOT saved (press c next time to keep them).")
    print("Photos per class (this person / everyone):")
    for c in CLASSES:
        print(f"  {c}: {counts[c][0]:3d} / {counts[c][1]:3d}")


# ---- Sample picture for the README -----------------------------------------

def make_samples(person):
    """Put one photo per class side by side in media/hand_samples_<person>.png."""
    tiles = []
    for c in CLASSES:
        files = sorted((DATA_DIR / c).glob(f"{person}_*.png"))
        if not files:
            sys.exit(f"No photos of class {c} for '{person}' yet.")
        img = cv2.imread(str(files[len(files) // 2]))   # one from the middle of the session
        img = cv2.copyMakeBorder(img, 26, 4, 4, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(img, c, (60, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        tiles.append(img)
    MEDIA_DIR.mkdir(exist_ok=True)
    out = MEDIA_DIR / f"hand_samples_{person}.png"
    cv2.imwrite(str(out), np.hstack(tiles))
    print(f"Saved {out}")


def main():
    parser = argparse.ArgumentParser(description="Take labeled 0-5 finger photos for the safe's network.")
    parser.add_argument("--list", action="store_true", help="show every camera and suggest the external webcam")
    parser.add_argument("--camera", type=int, help="camera number from --list (default: the one saved with the box)")
    parser.add_argument("--person", help="whose hand this is; goes into every file name")
    parser.add_argument("--samples", action="store_true", help="make the README sample picture for --person")
    args = parser.parse_args()

    if args.list:
        list_cameras()
    elif args.samples:
        if not args.person:
            sys.exit("--samples needs --person.")
        make_samples(clean_person(args.person))
    else:
        if not args.person:
            sys.exit("Please say whose hand it is, e.g.  --person mohammed")
        capture(args.camera, clean_person(args.person))


if __name__ == "__main__":
    main()
