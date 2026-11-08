"""
hand_crop.py - the ONE place that decides how a camera frame becomes a hand photo.

capture.py uses it to save training photos, and the training code and the
UNO Q app will use this same file. That way every image the network ever
sees (while learning and while guarding the safe) is cut out and shrunk in
exactly the same way. If training photos and live photos were prepared even
slightly differently (a box a few pixels off, a different shrinking method),
the network would be looking at a kind of picture it never practiced on and
would guess worse, without any error message to warn us.

The crop box is stored in crop_config.json, next to this file.
"""
import json
from datetime import datetime
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "crop_config.json"

# The camera is FORCED to this video size, and every picture is checked. 640x480
# is a mode almost every USB webcam supports, and it is light enough for the UNO Q
# to read live. The same camera can show a different slice of the desk at a
# different picture shape (a wide 640x360 picture shows more desk side to side
# than a 640x480 one), so a box saved for one shape cuts out the wrong area in
# another. That really happened: one session silently switched to 640x360 after
# starting at 640x480. So nothing here ever "adjusts" to another size: a wrong
# size is an error. The UNO Q app must force and check this same size.
FRAME_W, FRAME_H = 640, 480


class FrameSizeError(Exception):
    """The camera is sending a picture size other than FRAME_W x FRAME_H."""

# Saved photos are IMAGE_SIZE x IMAGE_SIZE pixels (see capture.py for why 128).
IMAGE_SIZE = 128


def open_camera(index):
    """Open camera number `index` and ask it for 640x480 video.

    The camera may not honor the request, or may change size later, so every
    frame must still go through check_frame_size().
    """
    cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    return cap


def check_frame_size(frame):
    """Raise FrameSizeError unless this picture is exactly FRAME_W x FRAME_H.

    Called on EVERY frame, not just the first: a camera can start at one size
    and switch to another a moment later.
    """
    h, w = frame.shape[:2]
    if (w, h) != (FRAME_W, FRAME_H):
        raise FrameSizeError(
            f"The camera is sending {w}x{h} pictures, but everything here must be "
            f"{FRAME_W}x{FRAME_H}. A different picture shape shows a different slice of "
            f"the desk, so photos would not match. Unplug the webcam, plug it back in, "
            f"close other apps using it (FaceTime, Zoom, Photo Booth), and try again.")


def clamp_box(x, y, size, frame_w, frame_h, min_size=64):
    """Keep a square box (top-left x, y and side length) fully inside the frame."""
    size = int(max(min_size, min(size, frame_w, frame_h)))
    x = int(max(0, min(x, frame_w - size)))
    y = int(max(0, min(y, frame_h - size)))
    return x, y, size


def crop_and_resize(frame, box, size=IMAGE_SIZE):
    """Cut the square box out of the frame and shrink it to size x size pixels.

    INTER_AREA shrinking averages the pixels being merged, which keeps edges
    (like finger outlines) smooth instead of jagged. Colors stay in OpenCV's
    order (blue, green, red), which is also what cv2.imwrite and cv2.imread use.
    """
    x, y, s = box
    crop = frame[y:y + s, x:x + s]
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)


def to_network_input(photo):
    """Turn a 128x128 photo (as saved by capture.py) into the numbers the network reads.

    - Checks the size, so a wrong-sized picture can never slip in.
    - Keeps OpenCV's blue-green-red color order (the photos on disk use it too).
    - Divides by 255, so each color value is 0.0 to 1.0 instead of 0 to 255:
      small numbers keep training steady, the same idea as rescaling the V data.
    - Reorders to channels-first (3 x 128 x 128), the layout PyTorch expects.
    Training, live_test.py and the UNO Q app all call this, so the network
    always gets its numbers prepared in exactly the same way.
    """
    if photo.shape != (IMAGE_SIZE, IMAGE_SIZE, 3):
        raise ValueError(f"expected a {IMAGE_SIZE}x{IMAGE_SIZE} color photo, got shape {photo.shape}")
    return (photo.astype("float32") / 255.0).transpose(2, 0, 1)


def frame_to_network_input(frame, box):
    """Camera frame -> checked size -> crop and shrink -> network numbers. The live path in one call."""
    check_frame_size(frame)
    return to_network_input(crop_and_resize(frame, box))


def save_config(camera_index, frame_w, frame_h, box, path=CONFIG_PATH):
    """Write the crop box to crop_config.json, with the picture size it belongs to.

    frame_w, frame_h must be the size of the picture the box was drawn on (the
    caller has already checked it is FRAME_W x FRAME_H). Anything that later
    uses the box refuses to run if its pictures are a different size.
    """
    x, y, s = box
    cfg = {
        "camera_index": camera_index,          # a hint only: camera numbers can change when devices are plugged in
        "frame_width": frame_w,                # the box only fits pictures of exactly this size
        "frame_height": frame_h,
        "box": {"x": x, "y": y, "size": s},
        "image_size": IMAGE_SIZE,
        "color_order": "BGR (OpenCV)",
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    return cfg


def load_config(path=CONFIG_PATH):
    """Read crop_config.json, or return None if it doesn't exist yet."""
    return json.loads(path.read_text()) if path.exists() else None


def box_from_config(cfg):
    """The saved box, as (x, y, size). Raises FrameSizeError if it was saved for another picture size.

    There is deliberately no "stretch the box to fit" fallback: a box moved to
    another picture shape would cut out a different slice of the desk.
    """
    saved = (cfg.get("frame_width"), cfg.get("frame_height"))
    if saved != (FRAME_W, FRAME_H):
        raise FrameSizeError(
            f"crop_config.json was saved for {saved[0]}x{saved[1]} pictures, not "
            f"{FRAME_W}x{FRAME_H}. Move it aside and line the box up again (f, then c).")
    b = cfg["box"]
    return clamp_box(b["x"], b["y"], b["size"], FRAME_W, FRAME_H)
