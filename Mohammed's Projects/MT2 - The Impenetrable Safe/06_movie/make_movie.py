"""
make_movie.py - the computer-made "stop-action movie": how the finger-counting
network turns one photo into the answer "2".

Run:  python make_movie.py          (takes a few minutes)
Out:  how_the_network_works.mp4     1920x1080, 30 frames per second, no sound
      scene_times.txt               when each scene starts, for writing the voiceover

Everything on screen is REAL, nothing is made up for the picture:
  * source_frame.png is a real 640x480 frame from the safe's own webcam (taken
    on the UNO Q, 2026-11-09), with Mohammed's hand showing 2 fingers.
  * It is cropped and shrunk with the same hand_crop.py the safe uses.
  * The filter weights, the feature maps, the multiply-and-add, the pooling
    and the six final scores all come from the trained network
    (03_training/finger_cnn.pt) running on that photo.
  * The training scene uses the real loss of every epoch of the training run
    that made finger_cnn.pt (training_loss.csv).
  * The ending shows the code only as dots: no real digits.

How it is made: each scene is a small function that draws ONE picture for a
given moment in time (in seconds). The main loop asks each scene for 30
pictures per second and writes them into the video file with OpenCV. The
pictures are drawn with Pillow (shapes and text) and numpy (images).
"""
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont
from matplotlib import colormaps

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "02_data_collection"))
sys.path.insert(0, str(PROJECT / "03_training"))
import hand_crop as hc                      # noqa: E402  (the safe's own crop and resize)
from model import load_trained, count_parameters    # noqa: E402

# ---- Settings ------------------------------------------------------------------
W, H, FPS = 1920, 1080, 30
OUT_VIDEO = HERE / "how_the_network_works_smooth.mp4"   # the first, smooth "slides" version
OUT_TIMES = HERE / "scene_times.txt"
FILTER = 2              # which layer-1 filter scene 3 shows (0-based: this is "filter 3").
                        # Chosen because on this photo its output is 63% negative and 37%
                        # positive, so the ReLU scene has something to remove.
TITLE_S = 2.0           # seconds for each title card

# Colours (red, green, blue), a calm dark look that reads well on a projector
BG = (22, 24, 29)
TEXT = (236, 238, 242)
DIM = (150, 156, 168)
GREEN = (63, 185, 80)
RED = (225, 70, 60)
BLUE = (60, 130, 235)
YELLOW = (230, 180, 60)
CHANNEL_COLOURS = [(90, 150, 255), (90, 200, 110), (240, 90, 80)]   # blue, green, red
CHANNEL_NAMES = ["blue", "green", "red"]     # the network's real order (OpenCV's BGR)

FONT_DIR = Path("/System/Library/Fonts")


def arrow_font(size):
    """Helvetica has no arrow character; the Mac's system font (San Francisco) does."""
    return ImageFont.truetype(str(FONT_DIR / "SFNS.ttf"), size)


def font(size, bold=False, mono=False):
    """Helvetica for words, Menlo (evenly spaced) for numbers."""
    if mono:
        return ImageFont.truetype(str(FONT_DIR / "Menlo.ttc"), size, index=1 if bold else 0)
    return ImageFont.truetype(str(FONT_DIR / "Helvetica.ttc"), size, index=1 if bold else 0)


# ---- The real data ---------------------------------------------------------------

frame_bgr = cv2.imread(str(HERE / "source_frame.png"))
hc.check_frame_size(frame_bgr)                       # the same 640x480 check as the safe
BOX = hc.box_from_config(hc.load_config())           # the saved crop box (x, y, size)
crop_bgr = hc.crop_and_resize(frame_bgr, BOX)        # 128x128, exactly as the safe does it
x_np = hc.to_network_input(crop_bgr)                 # 3x128x128, values 0..1 (blue, green, red)

model, info = load_trained(PROJECT / "03_training" / "finger_cnn.pt")
x_t = torch.from_numpy(x_np).unsqueeze(0)
with torch.no_grad():
    scores, maps = model.forward_with_maps(x_t)                  # maps: after ReLU, before pooling
    pre1 = F.conv2d(x_t, model.conv1.weight, model.conv1.bias, padding=1)[0].numpy()  # before ReLU
    pooled3 = F.max_pool2d(maps[2], 2)[0].numpy()                # 32x16x16: what the final layer reads
probs = torch.softmax(scores, 1)[0].numpy()
maps = [m[0].numpy() for m in maps]                              # 8x128x128, 16x64x64, 32x32x32
W1 = model.conv1.weight[FILTER].detach().numpy()                 # 3x3x3: the filter's 27 weights
B1 = float(model.conv1.bias[FILTER].detach())
out_pre = pre1[FILTER]                                           # the filter's map before ReLU
out_relu = maps[0][FILTER]                                       # ... and after ReLU (= max(0, pre))
pooled1 = F.max_pool2d(torch.from_numpy(out_relu)[None, None], 2)[0, 0].numpy()   # 64x64
N_PARAMS = count_parameters(model)

# The spot scene 3 works out by hand: where this filter answers most strongly
# in the finger area (rows 8-90: the fingers are in the top part of the photo).
# Not at the very edge, where the filter's window hangs over the border, and
# not the red tape at the bottom: a finger edge is the clearest example.
_inner = out_pre[8:90, 8:120]
SPOT = tuple(int(v) + 8 for v in np.unravel_index(np.argmax(_inner), _inner.shape))   # (row, col)
# Check the hand-worked sum equals the network's own number (it must, to the last digit)
_pad = np.pad(x_np, ((0, 0), (1, 1), (1, 1)))
_patch = _pad[:, SPOT[0]:SPOT[0] + 3, SPOT[1]:SPOT[1] + 3]        # the 3x3x3 numbers under the filter
assert abs((_patch * W1).sum() + B1 - out_pre[SPOT]) < 1e-4, "hand-worked sum doesn't match"

loss_rows = [l.split(",") for l in (HERE / "training_loss.csv").read_text().splitlines()
             if l and l[0].isdigit()]
EPOCHS = np.array([int(r[0]) for r in loss_rows])
TRAIN_LOSS = np.array([float(r[1]) for r in loss_rows])
VAL_LOSS = np.array([float(r[3]) for r in loss_rows])
BEST_EPOCH = int(info["epoch"])

print(f"photo guessed {probs.argmax()} at {probs.max():.1%}; filter {FILTER + 1}; spot {SPOT}; "
      f"{len(EPOCHS)} epochs of loss; {N_PARAMS:,} parameters")


# ---- Small drawing helpers ----------------------------------------------------------

def ease(t):
    """0..1 -> 0..1, starting and stopping gently (no sudden jumps)."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def phase(t, start, end):
    """How far t is through [start, end], as 0..1 (eased)."""
    return ease((t - start) / (end - start))


def lerp(a, b, f):
    return a + (b - a) * f


def rgb(img_bgr):
    return img_bgr[:, :, ::-1]


def blank():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def paste(img, arr, x, y, size=None, nearest=True, alpha=1.0):
    """Place a numpy picture (RGB) on the frame, optionally resized; blocky (nearest) shows real pixels."""
    if size is not None:
        arr = cv2.resize(arr, size, interpolation=cv2.INTER_NEAREST if nearest else cv2.INTER_AREA)
    pic = Image.fromarray(np.ascontiguousarray(arr.astype(np.uint8)))
    if alpha >= 1:
        img.paste(pic, (int(x), int(y)))
    else:
        region = img.crop((int(x), int(y), int(x) + pic.width, int(y) + pic.height))
        img.paste(Image.blend(region, pic, alpha), (int(x), int(y)))


def caption(d, text, alpha=1.0):
    """The short caption near the bottom of the screen."""
    col = tuple(int(lerp(b, c, alpha)) for b, c in zip(BG, TEXT))
    d.text((W // 2, 1000), text, font=font(46), fill=col, anchor="mm")


def label(d, xy, text, size=30, colour=DIM, bold=False, anchor="mm", mono=False):
    d.text(xy, text, font=font(size, bold, mono), fill=colour, anchor=anchor)


def captions(d, t, items):
    """Show the caption whose time has come: items = [(start time, text), ...], with a short fade-in."""
    current = [(s, txt) for s, txt in items if t >= s]
    if current:
        s, txt = current[-1]
        caption(d, txt, min(1.0, (t - s) / 0.4))


def diverging(v, vmax):
    """Colour for a signed number: red = negative, white = zero, blue = positive."""
    f = np.clip(v / vmax, -1, 1)[..., None]
    white = np.array([245, 245, 245], float)
    pos = white + (np.array(BLUE, float) - white) * np.clip(f, 0, 1)
    neg = white + (np.array(RED, float) - white) * np.clip(-f, 0, 1)
    return np.where(f >= 0, pos, neg)


MAGMA = (colormaps["magma"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)


def magma(m):
    """A feature map in the magma colours, each map scaled to its own brightest point."""
    top = m.max()
    idx = (np.clip(m / top, 0, 1) * 255).astype(int) if top > 0 else np.zeros(m.shape, int)
    return MAGMA[idx]


# ---- Title card ------------------------------------------------------------------------

def title_card(title, subtitle):
    def draw(t):
        img, d = blank()
        a = min(phase(t, 0, 0.4), 1 - phase(t, TITLE_S - 0.35, TITLE_S))   # fade in, then out
        c = tuple(int(lerp(b, x, a)) for b, x in zip(BG, TEXT))
        s = tuple(int(lerp(b, x, a)) for b, x in zip(BG, DIM))
        d.text((W // 2, H // 2 - 30), title, font=font(96, bold=True), fill=c, anchor="mm")
        d.text((W // 2, H // 2 + 60), subtitle, font=font(40), fill=s, anchor="mm")
        return img
    return draw


# ---- Scene 1: the photo -------------------------------------------------------------------

def scene_photo(t):
    img, d = blank()
    bx, by, bs = BOX
    # The camera frame, 1.5x, on the left half
    fs = 1.5
    fx, fy = 140, 170
    paste(img, rgb(frame_bgr), fx, fy, (int(640 * fs), int(480 * fs)), nearest=False,
          alpha=phase(t, 0, 0.6))
    label(d, (fx + 480, fy - 35), "the webcam: 640 × 480 pixels", 30, alpha_colour(t, 0.4))
    # The saved crop box appears around the red square
    if t > 2.0:
        a = phase(t, 2.0, 2.8)
        col = tuple(int(lerp(b, g, a)) for b, g in zip(BG, GREEN))
        d.rectangle([fx + bx * fs, fy + by * fs, fx + (bx + bs) * fs, fy + (by + bs) * fs], outline=col, width=5)
    # The crop lifts out and shrinks to 128 x 128 on the right
    if t > 4.0:
        f = phase(t, 4.0, 6.0)
        start = (fx + bx * fs, fy + by * fs, bs * fs)             # where the box is on screen
        end = (1260, 300, 512)                                    # 128 pixels shown 4x larger
        x0, y0, size = (lerp(s, e, f) for s, e in zip(start, end))
        crop_hi = rgb(frame_bgr[by:by + bs, bx:bx + bs])
        if f < 1:
            paste(img, crop_hi, x0, y0, (int(size), int(size)), nearest=False)
        else:                                                     # arrived: show the real 128x128 pixels
            paste(img, rgb(crop_bgr), x0, y0, (512, 512), nearest=True)
            d.rectangle([x0 - 2, y0 - 2, x0 + 514, y0 + 514], outline=GREEN, width=3)
            label(d, (x0 + 256, y0 + 560), "128 × 128 pixels", 34, TEXT, bold=True)
    captions(d, t, [(0.3, "The safe's webcam looks down at the red square"),
                    (2.0, "A saved box marks the red square"),
                    (4.0, "The box is cut out and shrunk to 128 × 128"),
                    (6.3, "This small picture is all the network ever sees")])
    return img


def alpha_colour(t, start):
    a = phase(t, start, start + 0.5)
    return tuple(int(lerp(b, c, a)) for b, c in zip(BG, DIM))


# ---- Scene 2: a photo is numbers ------------------------------------------------------------

PN = 8                  # patch size


def most_varied_patch():
    """The 8x8 patch (in the finger area) whose brightness varies most: a finger's edge."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY).astype(float)
    best, where = -1.0, (0, 0)
    for r in range(8, 90, 2):
        for c in range(8, 118, 2):
            v = gray[r:r + PN, c:c + PN].std()
            if v > best:
                best, where = v, (r, c)
    return where


PATCH = most_varied_patch()   # top-left (row, col) of the patch zoomed into


def view(img128, vx, vy, vw, out=768):
    """Show the square region (vx, vy, vw) of a 128x128 picture at out x out, with blocky pixels."""
    s = out / vw
    # The half-pixel terms line the enlarged pixels up exactly with the grid
    # lines drawn on top (OpenCV measures from pixel centres, not corners).
    m = np.float32([[s, 0, (0.5 - vx) * s - 0.5], [0, s, (0.5 - vy) * s - 0.5]])
    return cv2.warpAffine(img128, m, (out, out), flags=cv2.INTER_NEAREST, borderValue=BG)


def scene_numbers(t):
    img, d = blank()
    pr, pc = PATCH
    crop = rgb(crop_bgr)
    X, Y, S = 576, 140, 768
    # 0-1.5 s: the whole photo with the patch marked; 1.5-4 s: zoom into the patch
    z = phase(t, 1.5, 4.0)
    vx, vy, vw = lerp(0, pc, z), lerp(0, pr, z), lerp(128, PN, z)
    if t < 6.5:
        paste(img, view(crop, vx, vy, vw), X, Y)
        if z < 0.05:
            s = S / 128
            d.rectangle([X + pc * s, Y + pr * s, X + (pc + PN) * s, Y + (pr + PN) * s], outline=YELLOW, width=4)
        # 4-6.5 s: grid and each pixel's 3 numbers
        if t > 4.0:
            a = phase(t, 4.0, 4.8)
            cell = S / PN
            for i in range(PN + 1):
                d.line([X + i * cell, Y, X + i * cell, Y + S], fill=(0, 0, 0), width=2)
                d.line([X, Y + i * cell, X + S, Y + i * cell], fill=(0, 0, 0), width=2)
            if a > 0:
                f = font(22, bold=True, mono=True)
                for r in range(PN):
                    for c in range(PN):
                        px = crop_bgr[pr + r, pc + c]               # blue, green, red
                        cx, cy = X + (c + 0.5) * cell, Y + (r + 0.5) * cell
                        for k in range(3):                        # dark outline: readable on any pixel colour
                            d.text((cx, cy - 26 + 26 * k), f"{px[k]:3d}", font=f, fill=CHANNEL_COLOURS[k],
                                   anchor="mm", stroke_width=3, stroke_fill=(10, 10, 10))
    else:
        # 6.5-10 s: the patch splits into three grids, one per colour
        a = phase(t, 6.5, 7.3)
        scaled = t > 8.7                                        # the last part: numbers divided by 255
        f = font(19 if scaled else 22, bold=True, mono=True)
        cell = 54
        for k in range(3):
            gx, gy = 120 + k * 590, 180
            label(d, (gx + 4 * cell, gy - 40), f"{CHANNEL_NAMES[k]}", 38, CHANNEL_COLOURS[k], bold=True)
            for r in range(PN):
                for c in range(PN):
                    v = int(crop_bgr[pr + r, pc + c, k])
                    x0, y0 = gx + c * cell, gy + r * cell
                    shade = tuple(int(v * cc / 255 * a + BG[i] * (1 - a)) for i, cc in enumerate(CHANNEL_COLOURS[k]))
                    d.rectangle([x0, y0, x0 + cell - 2, y0 + cell - 2], fill=shade)
                    txt = f"{v / 255:.2f}"[1:] if scaled else f"{v}"
                    if scaled and v == 255:
                        txt = "1.0"
                    d.text((x0 + cell / 2, y0 + cell / 2), txt, font=f, fill=TEXT if a > 0.5 else BG, anchor="mm")
        label(d, (W // 2, 700), "128 × 128 pixels × 3 colours = 49,152 numbers", 52, TEXT, bold=True)
    captions(d, t, [(0.3, "Zoom into a fingertip's edge"),
                    (4.0, "Every pixel is 3 numbers: blue, green, red (0 to 255)"),
                    (6.5, "So the photo is just three grids of numbers"),
                    (8.7, "Divided by 255, they become 0 to 1: the network's input")])
    return img


# ---- Scene 3: convolution -----------------------------------------------------------------------

IN_X, IN_Y, MAP_S = 70, 190, 512          # input photo on the left (128 px shown 4x)
OUT_X = W - 70 - MAP_S                    # output map on the right
SPOT_I = SPOT[0] * 128 + SPOT[1]          # the spot's place in left-to-right, top-to-bottom order
VMAX = float(np.percentile(np.abs(out_pre), 99))   # colour scale: the strongest 1% just saturate,
                                                   # so one very strong edge doesn't wash out the rest
OUT_COLOURED = diverging(out_pre, VMAX).astype(np.uint8)


def sweep_position(t):
    """How many output pixels are done at time t: sweep to the spot, pause there, then finish."""
    if t < 4.0:
        return int(SPOT_I * phase(t, 0.3, 4.0))
    if t < 11.0:
        return SPOT_I
    return int(lerp(SPOT_I, 128 * 128, phase(t, 11.0, 13.0)))


def weight_grid(d, x, y, w, cell=64, size=18):
    """A 3x3 grid of weights: blue tint for positive, red for negative."""
    f = font(size, bold=True, mono=True)
    for r in range(3):
        for c in range(3):
            v = w[r, c]
            colour = tuple(int(x_) for x_ in diverging(np.array(v), 0.6))
            d.rectangle([x + c * cell, y + r * cell, x + (c + 1) * cell - 3, y + (r + 1) * cell - 3], fill=colour)
            d.text((x + (c + 0.5) * cell, y + (r + 0.5) * cell), f"{v:+.2f}", font=f, fill=(20, 20, 20), anchor="mm")


def scene_conv(t):
    img, d = blank()
    pos = sweep_position(t)
    r, c = divmod(min(pos, 128 * 128 - 1), 128)
    # Left: the photo, with the filter's 3x3 window at the current spot
    paste(img, rgb(crop_bgr), IN_X, IN_Y, (MAP_S, MAP_S))
    s = MAP_S / 128
    d.rectangle([IN_X + (c - 1) * s, IN_Y + (r - 1) * s, IN_X + (c + 2) * s, IN_Y + (r + 2) * s],
                outline=YELLOW, width=3)
    label(d, (IN_X + MAP_S / 2, IN_Y - 35), "the photo (128 × 128 × 3)")
    # Right: the output map, filled in up to the current spot
    out = np.full((128, 128, 3), 45, np.uint8)
    flat = out.reshape(-1, 3)
    flat[:pos] = OUT_COLOURED.reshape(-1, 3)[:pos]
    paste(img, out, OUT_X, IN_Y, (MAP_S, MAP_S))
    d.rectangle([OUT_X + c * s - 2, IN_Y + r * s - 2, OUT_X + (c + 1) * s + 2, IN_Y + (r + 1) * s + 2],
                outline=YELLOW, width=3)
    label(d, (OUT_X + MAP_S / 2, IN_Y - 35), f"filter {FILTER + 1}'s output map")
    # Middle: the filter's real weights, one 3x3 grid per colour
    mx = 625                                                  # three 192-pixel grids with 40-pixel gaps
    label(d, (W // 2, 150), f"layer-1 filter {FILTER + 1}: 3 × 3 weights for each colour, plus a bias",
          28, TEXT, bold=True)
    for k in range(3):
        gx = mx + k * 232
        label(d, (gx + 96, 195), CHANNEL_NAMES[k], 26, CHANNEL_COLOURS[k], bold=True)
        weight_grid(d, gx, 215, W1[k])
    label(d, (W // 2, 425), f"bias {B1:+.2f}", 26, DIM)
    # 4-11 s: the multiply-and-add at the spot, worked out
    if 4.0 <= t < 11.0:
        patch = _patch
        f = font(18, bold=True, mono=True)
        a = phase(t, 4.0, 4.6)
        for k in range(3):
            gx = mx + k * 232
            label(d, (gx + 96, 470), "pixel" if t < 6.0 else "pixel × weight", 22, DIM)
            for rr in range(3):
                for cc in range(3):
                    prod = patch[k, rr, cc] * W1[k, rr, cc]
                    x0, y0 = gx + cc * 64, 490 + rr * 46
                    d.rectangle([x0, y0, x0 + 61, y0 + 43], fill=(40, 43, 50))
                    txt = f"{patch[k, rr, cc]:.2f}" if t < 6.0 else f"{prod:+.2f}"
                    d.text((x0 + 31, y0 + 22), txt, font=f, fill=TEXT if a > 0.5 else BG, anchor="mm")
            if t >= 7.0:
                ssum = (patch[k] * W1[k]).sum()
                label(d, (gx + 96, 655), f"sum {ssum:+.2f}", 26, CHANNEL_COLOURS[k], bold=True)
        if t >= 8.5:
            sums = [(patch[k] * W1[k]).sum() for k in range(3)]
            total = sum(sums) + B1
            label(d, (W // 2, 720), f"{sums[0]:+.2f} {sums[1]:+.2f} {sums[2]:+.2f}  (bias) {B1:+.2f}", 30, TEXT)
            label(d, (W // 2, 785), f"= {total:+.2f}", 54, YELLOW, bold=True)
            label(d, (W // 2, 845), "one number in the output map", 26, DIM)
    captions(d, t, [(0.3, "A filter is a small grid of weights that slides over the photo"),
                    (4.0, "At each spot: the 27 pixel numbers under it..."),
                    (6.0, "...each times its weight..."),
                    (7.0, "...added up..."),
                    (8.5, "...plus a bias gives ONE output number"),
                    (11.0, "Done at every spot, it paints a new picture: a feature map")])
    return img


# ---- Scene 4: ReLU -------------------------------------------------------------------------------

def scene_relu(t):
    img, d = blank()
    f = phase(t, 1.8, 4.2)                                        # red fades to white
    shown = np.where(out_pre < 0, out_pre * (1 - f), out_pre)
    paste(img, diverging(shown, VMAX), 200, 170, (640, 640))
    label(d, (520, 135), f"filter {FILTER + 1}'s output map")
    # Legend and two real examples from this map
    lx = 1020
    label(d, (lx, 260), "red = negative", 40, RED, bold=True, anchor="lm")
    label(d, (lx, 320), "blue = positive", 40, BLUE, bold=True, anchor="lm")
    neg, pos = float(out_pre.min()), float(out_pre.max())
    if t > 1.0:
        label(d, (lx, 470), "ReLU:  keep positives, negatives become 0", 36, TEXT, bold=True, anchor="lm")
        newneg = lerp(neg, 0.0, f)
        label(d, (lx, 560), f"{neg:+.2f}  →  {newneg:+.2f}" if f < 1 else f"{neg:+.2f}  →  0", 44,
              RED if f < 1 else TEXT, anchor="lm", mono=True)
        label(d, (lx, 630), f"{pos:+.2f}  →  {pos:+.2f}", 44, BLUE, anchor="lm", mono=True)
    neg_share = np.mean(out_pre < 0)
    captions(d, t, [(0.3, f"{neg_share:.0%} of this map came out negative"),
                    (1.8, "ReLU turns every negative number into 0"),
                    (4.3, "Only the \"I found my pattern here\" signals go on")])
    return img


# ---- Scene 5: pooling ------------------------------------------------------------------------------

POOL_AT = tuple(min(max(v // 2 * 2 - 2, 0), 120) for v in SPOT)   # an 8x8 region near the strong spot
                                                                  # (even, so the 2x2 blocks line up; kept on the map)


def scene_pool(t):
    img, d = blank()
    r0, c0 = POOL_AT
    region = out_relu[r0:r0 + 8, c0:c0 + 8]
    top = float(np.percentile(out_relu, 99))                  # same colour scale idea as scene 3
    cell = 70
    X, Y = 90, 230
    f = font(19, bold=True, mono=True)
    label(d, (X + 4 * cell, Y - 40), "an 8 × 8 piece of the map (after ReLU)", 28)
    n_blocks = int(lerp(0, 16, phase(t, 0.5, 4.5)))            # how many 2x2 blocks are done
    for r in range(8):
        for c in range(8):
            v = float(region[r, c])
            colour = tuple(int(x) for x in diverging(np.array(v), top))
            d.rectangle([X + c * cell, Y + r * cell, X + (c + 1) * cell - 3, Y + (r + 1) * cell - 3], fill=colour)
            d.text((X + (c + 0.5) * cell, Y + (r + 0.5) * cell), f"{v:.2f}", font=f, fill=(20, 20, 20), anchor="mm")
    # Result grid 4x4, filled block by block; the current block is outlined, its biggest number circled
    RX, RY = 760, Y + 140
    label(d, (RX + 2 * cell, RY - 40), "keep the biggest", 28)
    for b in range(16):
        br, bc = divmod(b, 4)
        block = region[br * 2:br * 2 + 2, bc * 2:bc * 2 + 2]
        if b < n_blocks:
            v = float(block.max())
            colour = tuple(int(x) for x in diverging(np.array(v), top))
            d.rectangle([RX + bc * cell, RY + br * cell, RX + (bc + 1) * cell - 3, RY + (br + 1) * cell - 3], fill=colour)
            d.text((RX + (bc + 0.5) * cell, RY + (br + 0.5) * cell), f"{v:.2f}", font=f, fill=(20, 20, 20), anchor="mm")
        else:
            d.rectangle([RX + bc * cell, RY + br * cell, RX + (bc + 1) * cell - 3, RY + (br + 1) * cell - 3], outline=(60, 64, 72), width=2)
        if b == n_blocks and n_blocks < 16:
            d.rectangle([X + bc * 2 * cell - 3, Y + br * 2 * cell - 3, X + (bc * 2 + 2) * cell, Y + (br * 2 + 2) * cell],
                        outline=YELLOW, width=5)
            mr, mc = np.unravel_index(np.argmax(block), block.shape)
            cx, cy = X + (bc * 2 + mc + 0.5) * cell, Y + (br * 2 + mr + 0.5) * cell
            d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline=YELLOW, width=4)
    # 5-8 s: the whole map, before and after: 128 -> 64
    if t > 5.0:
        a = phase(t, 5.0, 5.8)
        paste(img, diverging(out_relu, top), 1150, 300, (384, 384), alpha=a)
        paste(img, diverging(pooled1, top), 1600, 396, (192, 192), alpha=a)
        label(d, (1342, 720), "128 × 128", 32, TEXT, bold=True)
        label(d, (1696, 720), "64 × 64", 32, TEXT, bold=True)
        d.text((1560, 492), "→", font=arrow_font(60), fill=TEXT, anchor="mm")
    captions(d, t, [(0.3, "Max pooling: look at each 2 × 2 block..."),
                    (2.0, "...and keep only the biggest number"),
                    (5.0, "The picture halves: 128 × 128 becomes 64 × 64"),
                    (6.5, "Less to compute, and a finger can move a little")])
    return img


# ---- Scene 6: going deeper ---------------------------------------------------------------------------

def map_grid(img, d, stack, cols, tile, gap, x, y, alpha):
    for i, m in enumerate(stack):
        r, c = divmod(i, cols)
        paste(img, magma(m), x + c * (tile + gap), y + r * (tile + gap), (tile, tile), alpha=alpha)


def scene_deeper(t):
    img, d = blank()
    panels = [  # (maps, cols, tile, gap, x, y, title, meaning, appears at)
        (maps[0], 4, 140, 8, 90, 380, "layer 1 · 8 maps · 128 × 128", "edges and colours", 0.3),
        (maps[1], 4, 84, 6, 790, 340, "layer 2 · 16 maps · 64 × 64", "finger shapes", 3.3),
        (maps[2], 8, 54, 4, 1290, 400, "layer 3 · 32 maps · 32 × 32", "fingers and gaps", 6.3),
    ]
    for stack, cols, tile, gap, x, y, title, meaning, at in panels:
        if t < at:
            continue
        a = phase(t, at, at + 0.8)
        map_grid(img, d, stack, cols, tile, gap, x, y, a)
        rows = (len(stack) + cols - 1) // cols
        w, h = cols * (tile + gap) - gap, rows * (tile + gap) - gap
        col = tuple(int(lerp(b, c, a)) for b, c in zip(BG, TEXT))
        d.text((x + w / 2, y - 40), title, font=font(28, bold=True), fill=col, anchor="mm")
        d.text((x + w / 2, y + h + 40), meaning, font=font(30), fill=tuple(int(lerp(b, c, a)) for b, c in zip(BG, YELLOW)), anchor="mm")
    for ax, at in ((720, 3.3), (1240, 6.3)):                    # arrows between the layers
        if t >= at:
            d.text((ax, 520), "→", font=arrow_font(60), fill=DIM, anchor="mm")
    captions(d, t, [(0.3, "Layer 1: 8 filters find simple edges and colours"),
                    (3.3, "Layer 2: 16 filters combine them into finger shapes"),
                    (6.3, "Layer 3: 32 filters see whole fingers and the gaps between them"),
                    (9.0, "Each layer: convolution, ReLU, pooling, smaller and smarter")])
    return img


# ---- Scene 7: the answer ---------------------------------------------------------------------------------

def scene_answer(t):
    img, d = blank()
    # Left: what the final layer reads, 32 small maps of 16 x 16
    a = phase(t, 0, 0.6)
    map_grid(img, d, pooled3, 8, 40, 4, 80, 330, a)
    label(d, (80 + 174, 290), "32 maps × 16 × 16", 28, TEXT, bold=True)
    label(d, (80 + 174, 540), "= 8,192 numbers", 34, YELLOW, bold=True)
    if t > 1.5:
        d.text((560, 430), "→", font=arrow_font(70), fill=DIM, anchor="mm")
        label(d, (720, 400), "final layer", 32, TEXT, bold=True)
        label(d, (720, 445), "8,192 × 6 weights", 26, DIM)
        d.text((880, 430), "→", font=arrow_font(70), fill=DIM, anchor="mm")
    # Right: the six real confidences grow
    g = phase(t, 2.0, 5.0)
    win = int(probs.argmax())
    BX, BY, BW, BH = 980, 820, 130, 560
    for i, p in enumerate(probs):
        h = BH * p * g
        colour = GREEN if (i == win and t > 5.3) else (110, 116, 128)
        x0 = BX + i * (BW + 22)
        d.rectangle([x0, BY - h, x0 + BW, BY], fill=colour)
        label(d, (x0 + BW / 2, BY + 35), str(i), 40, TEXT, bold=True)
        if g > 0.05:
            label(d, (x0 + BW / 2, BY - h - 28), f"{p * g:.0%}" if p * g >= 0.005 else "0%", 28, TEXT)
    label(d, (BX + 3 * (BW + 22) - 11, BY + 85), "number of fingers", 28)
    if t > 5.3:
        d.text((BX + 3 * (BW + 22), 180), f"{win} fingers  ({probs[win]:.0%} sure)",
               font=font(64, bold=True), fill=GREEN, anchor="mm")
    captions(d, t, [(0.3, "Everything left: 8,192 numbers"),
                    (1.5, "The final layer weighs them all into 6 scores, one per answer"),
                    (5.3, "The biggest wins: two fingers")])
    return img


# ---- Bonus scene: how it learned ----------------------------------------------------------------------------

def scene_training(t):
    img, d = blank()
    X0, X1, Y0, Y1 = 220, 1700, 230, 830                       # plot area
    top = float(max(TRAIN_LOSS.max(), VAL_LOSS.max())) * 1.05
    def pt(epoch, loss):
        return (X0 + (epoch - 1) / (len(EPOCHS) - 1) * (X1 - X0), Y1 - loss / top * (Y1 - Y0))
    d.line([X0, Y1, X1, Y1], fill=DIM, width=3)
    d.line([X0, Y0, X0, Y1], fill=DIM, width=3)
    label(d, ((X0 + X1) / 2, Y1 + 50), "epoch (one pass over the 816 training photos)", 30)
    label(d, (X0 - 30, Y0 - 40), "loss (how wrong)", 30, anchor="lm")
    for e in (1, 20, 40, 60, 80):
        x, _ = pt(e, 0)
        label(d, (x, Y1 + 18), str(e), 22)
    # The real loss curve, drawn up to where the ball is
    prog = phase(t, 0.5, 7.0)
    upto = 1 + prog * (len(EPOCHS) - 1)
    n = int(upto)
    pts = [pt(e, l) for e, l in zip(EPOCHS[:n], TRAIN_LOSS[:n])]
    if len(pts) > 1:
        d.line(pts, fill=BLUE, width=5, joint="curve")
    vpts = [pt(e, l) for e, l in zip(EPOCHS[:n], VAL_LOSS[:n])]
    if len(vpts) > 1:
        d.line(vpts, fill=(120, 90, 90), width=2)
    # The ball: on the training curve, between epochs
    i = min(int(upto) - 1, len(EPOCHS) - 2)
    frac = upto - 1 - i
    bxy = pt(lerp(EPOCHS[i], EPOCHS[i + 1], frac), lerp(TRAIN_LOSS[i], TRAIN_LOSS[i + 1], frac))
    d.ellipse([bxy[0] - 18, bxy[1] - 18, bxy[0] + 18, bxy[1] + 18], fill=YELLOW)
    label(d, (X1 - 10, Y0 + 10), "training photos", 26, BLUE, anchor="rm")
    label(d, (X1 - 10, Y0 + 50), "validation photos (never learned from)", 26, (170, 120, 120), anchor="rm")
    if upto >= BEST_EPOCH:
        x, y = pt(BEST_EPOCH, VAL_LOSS[BEST_EPOCH - 1])
        d.line([x, Y0 + 90, x, Y1], fill=GREEN, width=2)
        label(d, (x, Y0 + 75), f"best: epoch {BEST_EPOCH}, saved", 26, GREEN, bold=True)
    captions(d, t, [(0.3, f"Where the weights come from: all {N_PARAMS:,} started random"),
                    (2.5, "Each pass, every weight is nudged downhill: a little less wrong"),
                    (5.5, "The ball is the real training run of this network")])
    return img


# ---- Ending: the code dots and UNLOCKED -------------------------------------------------------------------

def scene_end(t):
    img, d = blank()
    for i in range(3):                                         # three dots, filled one by one (no digits)
        cx, cy = W // 2 + (i - 1) * 140, 380
        filled = t > 0.6 + i * 0.7
        if filled:
            d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=TEXT)
        else:
            d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=DIM, width=5)
    if t > 2.8:
        a = phase(t, 2.8, 3.4)
        col = tuple(int(lerp(b, g, a)) for b, g in zip(BG, GREEN))
        # an open padlock: body plus a raised shackle
        px, py = W // 2 - 470, 560
        d.rounded_rectangle([px - 55, py + 30, px + 55, py + 120], 12, fill=col)
        d.arc([px - 5, py - 75, px + 85, py + 45], 180, 360, fill=col, width=14)
        d.line([px + 78, py - 15, px + 78, py + 10], fill=col, width=14)
        d.text((W // 2 + 90, py + 60), "UNLOCKED", font=font(120, bold=True), fill=col, anchor="mm")
    captions(d, t, [(0.3, "Three digits, each counted by the network..."),
                    (2.8, "...and the latch swings open")])
    return img


# ---- Putting it together -------------------------------------------------------------------------------------

SCENES = [  # (title, subtitle, drawing function, seconds)
    ("The photo", "what the camera sees", scene_photo, 8.0),
    ("A photo is numbers", "49,152 of them", scene_numbers, 10.0),
    ("Convolution", "a filter slides over the photo", scene_conv, 14.0),
    ("ReLU", "negatives become zero", scene_relu, 6.0),
    ("Pooling", "keep the biggest, halve the picture", scene_pool, 8.0),
    ("Going deeper", "three layers, smaller and smarter", scene_deeper, 10.0),
    ("The answer", "six scores, one winner", scene_answer, 8.0),
    ("How it learned", "rolling downhill", scene_training, 8.0),
    ("Unlocked", "", scene_end, 5.0),
]


def fade_in(img, t, seconds=0.3):
    """Scenes start from the background colour instead of jumping in."""
    a = min(1.0, t / seconds)
    if a >= 1:
        return img
    return Image.blend(Image.new("RGB", (W, H), BG), img, a)


def main():
    writer = cv2.VideoWriter(str(OUT_VIDEO), cv2.VideoWriter_fourcc(*"avc1"), FPS, (W, H))   # H.264: plays in QuickTime and iMovie
    if not writer.isOpened():
        sys.exit("Could not open the video writer (H.264).")
    clock, times = 0.0, []
    for title, subtitle, draw, seconds in SCENES:
        times.append((clock, title, clock + TITLE_S))
        for part, length in ((title_card(title, subtitle), TITLE_S), (draw, seconds)):
            for i in range(int(round(length * FPS))):
                t = i / FPS
                img = part(t)
                if part is draw:
                    img = fade_in(img, t)
                writer.write(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR))
            clock += length
        print(f"{title}: done")
    writer.release()

    def mmss(s):
        return f"{int(s // 60)}:{s % 60:04.1f}"
    lines = ["Scene start times for the voiceover (minutes:seconds).",
             "Each scene opens with a 2-second title card; 'content' is when its pictures start.", ""]
    lines += [f"{mmss(s):>7}  {title:<20} (content from {mmss(c)})" for s, title, c in times]
    lines += ["", f"{mmss(clock):>7}  end  (total {clock:.0f} s)"]
    OUT_TIMES.write_text("\n".join(lines) + "\n")
    print(f"Saved {OUT_VIDEO.name} ({clock:.0f} s) and {OUT_TIMES.name}")


if __name__ == "__main__":
    main()
