"""
make_stopmotion.py - the network movie as a digital stop-motion "paper cutout" film.

Run:  python make_stopmotion.py              the whole movie (about 3 minutes) + contact sheet
      python make_stopmotion.py --test conv  a 5-second test of the convolution scene
      python make_stopmotion.py --sheet      only remake contact_sheet.png from the MP4
Out:  how_the_network_works.mp4   1920x1080, 12 frames per second, no sound
      contact_sheet.png           two frames per scene, for reviewing
      scene_times.txt             unchanged: the scenes start exactly when they did

Same 9 scenes, same lengths, same REAL numbers as the smooth version: all the
data (the photo, the filter weights, the feature maps, the scores, the
training loss) is taken from make_movie.py, which computes it from the
trained network. Only the look changes.

How the stop-motion look is made:
  * 12 frames per second, and every pose is held for 2 frames (like shooting
    "on twos"), so things move in visible jumps, 6 times a second.
  * Every piece is a paper cutout: a white paper border, a soft shadow on
    the desk, and a tiny random tilt and shift that changes every frame, as
    if each piece had been nudged by hand between photos.
  * The background is a real photo of paper on a desk (background_paper.png,
    cleaned by clean_background.py), with a soft dark vignette and a gentle
    flicker in the light, like a phone filming a desk.
  * Words are in a marker font (Marker Felt) on paper notes held by tape;
    numbers are handwritten (Noteworthy) on index cards.
  * Pieces slide in from the edges, and out again, in steps.
"""
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_movie as real          # the real data and the scene list (lengths, titles)

HERE = Path(__file__).resolve().parent
W, H = 1920, 1080
FPS = 12                           # stop-motion rate
HOLD = 2                           # each pose is held for 2 frames ("on twos")
OUT_VIDEO = HERE / "how_the_network_works.mp4"
SAFE_PHOTO = HERE / "safe_photo.jpg"                  # the real photo of the safe, for the ending (copied from the Desktop)

INK = (40, 40, 48)                 # marker ink
PAPER = (251, 250, 246)            # white paper
NOTE_YELLOW = (252, 238, 150)      # sticky notes
CARDBOARD = (176, 134, 88)
TAPE = (236, 228, 190, 150)        # see-through tape
GREEN, RED, BLUE = (46, 150, 70), (205, 60, 50), (45, 105, 200)
CHANNEL_INK = [(40, 90, 200), (40, 140, 60), (200, 55, 45)]           # blue, green, red
CHANNEL_PAPER = [(214, 228, 250), (214, 240, 214), (250, 218, 214)]   # pale tinted paper per channel
CHANNEL_NAMES = real.CHANNEL_NAMES

FONTS = Path("/System/Library/Fonts")


def marker(size):
    """Marker Felt Wide: titles, captions, labels."""
    return ImageFont.truetype(str(FONTS / "MarkerFelt.ttc"), size, index=1)


def hand(size):
    """Noteworthy Bold: handwritten numbers (clearer than a marker at small sizes)."""
    return ImageFont.truetype(str(FONTS / "Noteworthy.ttc"), size, index=1)


def symbols(size):
    """The system font: has the arrow and times characters."""
    return ImageFont.truetype(str(FONTS / "SFNS.ttf"), size)


# ---- The desk: background, vignette, flicker -------------------------------------------------

_paper = cv2.imread(str(HERE / "background_paper.png"))[:, :, ::-1]          # RGB
_bh, _bw = _paper.shape[:2]
BACKGROUND = _paper[(_bh - H) // 2:(_bh - H) // 2 + H, (_bw - W) // 2:(_bw - W) // 2 + W].astype(np.float32)
_yy, _xx = np.mgrid[0:H, 0:W]
_r = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2) / np.sqrt(2)
VIGNETTE = (1 - 0.30 * _r ** 2.2)[..., None].astype(np.float32)               # darker towards the corners


def rng_for(key, frame):
    """The same random numbers for the same piece and frame, every time the movie is made."""
    return np.random.default_rng(zlib.crc32(f"{key}|{frame}".encode()))


def desk(frame):
    """The desk for one frame: the paper photo with a vignette and a gentle flicker of the light.

    Only the desk gets these. The cutouts are laid on top afterwards, so the
    photos and maps keep their true colours (no darkening in the corners).
    """
    flicker = 1 + rng_for("light", frame).normal(0, 0.008)
    arr = np.clip(BACKGROUND * VIGNETTE * flicker, 0, 255).astype(np.uint8)
    return Image.fromarray(arr).convert("RGBA")


# ---- Paper cutouts --------------------------------------------------------------------------------

_cache = {}


def cached(key, make):
    """Pieces are drawn once and reused (they change only when their content changes)."""
    if key not in _cache:
        _cache[key] = make()
    return _cache[key]


def to_rgba(img):
    if isinstance(img, np.ndarray):
        img = Image.fromarray(np.ascontiguousarray(img.astype(np.uint8)))
    return img.convert("RGBA")


def cutout(content, border=12, paper=PAPER):
    """Put a white paper border around a picture (numpy RGB or PIL)."""
    content = to_rgba(content)
    w, h = content.size
    card = Image.new("RGBA", (w + 2 * border, h + 2 * border), paper + (255,))
    card.alpha_composite(content, (border, border))
    return card


def taped(card, strips=2):
    """Add see-through tape strips across the top corners (they stick out past the card)."""
    m = 26
    w, h = card.size
    out = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    out.alpha_composite(card, (m, m))
    tape = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(tape)
    # Tape is centred just outside each top corner, so only its end crosses the card:
    # it holds the corner and never reaches the writing (notes keep 46-pixel side margins).
    spots = [(m - 4, m - 2, -35), (w + m + 4, m - 2, 35)][:strips]
    length = int(min(92, max(50, 0.2 * w)))            # tape in proportion to the card
    for cx, cy, ang in spots:
        piece = Image.new("RGBA", (length, 28), TAPE)
        piece = piece.rotate(ang, expand=True, resample=Image.BICUBIC)
        tape.alpha_composite(piece, (int(cx - piece.width / 2), int(cy - piece.height / 2)))
    out.alpha_composite(tape)
    return out


def note(text, size=44, paper=PAPER, ink=INK, pad=(46, 18), font=None, tape=True, width=None):
    """A paper note with marker writing (and tape)."""
    f = font or marker(size)
    if font is None:
        text = text.replace("×", "x")         # Marker Felt has no times sign; a hand-written x reads the same
    lines = text.split("\n")
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    boxes = [probe.textbbox((0, 0), ln, font=f) for ln in lines]
    tw = max(b[2] - b[0] for b in boxes)
    lh = int(size * 1.25)
    w = max(width or 0, tw + 2 * pad[0])
    h = lh * len(lines) + 2 * pad[1]
    img = Image.new("RGBA", (w, h), paper + (255,))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((w / 2, pad[1] + lh * (i + 0.5)), ln, font=f, fill=ink, anchor="mm")
    return taped(img) if tape else img


def place(canvas, piece, cx, cy, key, frame, tilt=0.0, wobble=1.0):
    """Lay a cutout on the desk, centred at (cx, cy), with its shadow and hand-placed wobble.

    The wobble (a fraction of a degree of tilt, a pixel or two of shift) is new
    every frame, like a piece nudged between photos; it is small enough that
    numbers stay readable.
    """
    r = rng_for(key, frame)
    angle = tilt + r.normal(0, 0.35) * wobble
    dx, dy = r.normal(0, 1.3, 2) * wobble
    rot = piece.rotate(angle, expand=True, resample=Image.BICUBIC)
    x, y = int(cx - rot.width / 2 + dx), int(cy - rot.height / 2 + dy)
    # Soft shadow: the piece's outline, blurred, darkened, shifted down-right
    alpha = rot.getchannel("A").filter(ImageFilter.GaussianBlur(7))
    shadow = Image.new("RGBA", rot.size, (30, 25, 20, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * 0.38)))
    canvas.alpha_composite(shadow, (x + 7, y + 9))
    canvas.alpha_composite(rot, (x, y))


# ---- Stepped movement -----------------------------------------------------------------------------

def ease_out(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 2


def slide(t, length, home, side, t_in=0.0, dur=0.6, t_out=None):
    """Where a piece is at time t: it slides in from an edge, stays, then slides out.

    t only changes 6 times a second (every pose is held for 2 frames), so the
    slide happens in a few visible jumps, never a smooth glide. Returns None
    while the piece is still off the desk.
    """
    if t < t_in:
        return None
    off = {"left": (-700, home[1]), "right": (W + 700, home[1]),
           "top": (home[0], -500), "bottom": (home[0], H + 500)}[side]
    p = ease_out((t - t_in) / dur)
    pos = (off[0] + (home[0] - off[0]) * p, off[1] + (home[1] - off[1]) * p)
    t_out = length - 0.55 if t_out is None else t_out
    if t >= t_out:
        q = min(1.0, (t - t_out) / 0.5) ** 2
        pos = (home[0] + (off[0] - home[0]) * q, home[1] + (off[1] - home[1]) * q)
        if q >= 1:
            return None
    return pos


def put(canvas, piece, t, length, home, side, key, frame, t_in=0.0, tilt=0.0, t_out=None, dur=0.6):
    """slide() + place(): the usual way a piece arrives, sits, and leaves."""
    pos = slide(t, length, home, side, t_in, dur, t_out)
    if pos is not None:
        place(canvas, piece, pos[0], pos[1], key, frame, tilt)


def caption(canvas, t, length, frame, items):
    """The caption: a paper strip near the bottom; each new caption slides up from the bottom."""
    current = [(s, txt) for s, txt in items if t >= s]
    if not current:
        return
    s, txt = current[-1]
    piece = cached(("cap", txt), lambda: note(txt, 40))
    tilt = (zlib.crc32(txt.encode()) % 7 - 3) * 0.4                       # each caption sits a bit crooked
    put(canvas, piece, t, length, (W / 2, 1000), "bottom", ("cap", txt), frame, t_in=s, tilt=tilt, dur=0.35)


def grid_card(values, fmt, cell, ink=INK, paper=PAPER, colours=None, size=24, lines=True):
    """Numbers handwritten in a grid on an index card. colours: an optional cell-fill per cell."""
    rows, cols = values.shape
    img = Image.new("RGBA", (cols * cell, rows * cell), paper + (255,))
    d = ImageDraw.Draw(img)
    f = hand(size)
    for r in range(rows):
        for c in range(cols):
            box = [c * cell, r * cell, (c + 1) * cell, (r + 1) * cell]
            if colours is not None:
                d.rectangle(box, fill=tuple(int(v) for v in colours[r, c]))
            if lines:
                d.rectangle(box, outline=(170, 175, 190), width=1)
            d.text(((c + 0.5) * cell, (r + 0.5) * cell), fmt(values[r, c]), font=f, fill=ink, anchor="mm")
    return cutout(img, border=10)


def pale(colour_rgb, amount=0.55):
    """A paler version of a colour (so handwriting on it stays readable)."""
    return tuple(int(c + (255 - c) * amount) for c in colour_rgb)


def signed_colours(v, vmax):
    """Pale red for negative, pale blue for positive, white for zero (like the map colours)."""
    return np.stack([np.array(real.diverging(np.array(x), vmax)) for x in v.ravel()]).reshape(v.shape + (3,)) * 0.6 + 255 * 0.4


# ---- Title card -------------------------------------------------------------------------------------

def title_card(title, subtitle):
    def draw(canvas, t, frame, length):
        piece = cached(("title", title), lambda: big_title(title, subtitle))
        pos = slide(t, length, (W / 2, H / 2 - 20), "top", 0.0, 0.5, length - 0.5)
        if pos:
            place(canvas, piece, pos[0], pos[1], ("title", title), frame, tilt=-1.5)
    return draw


def big_title(title, subtitle):
    img = Image.new("RGBA", (1150, 340), PAPER + (255,))
    d = ImageDraw.Draw(img)
    d.text((575, 140), title, font=marker(104), fill=INK, anchor="mm")
    if subtitle:
        d.text((575, 250), subtitle, font=hand(44), fill=(90, 90, 100), anchor="mm")
    return taped(img)


# ---- Scene 1: the photo ---------------------------------------------------------------------------

def s_photo(canvas, t, frame, L):
    fs = 1.4
    fw, fh = int(640 * fs), int(480 * fs)
    home = (130 + fw / 2 + 12, 160 + fh / 2 + 12)
    print_piece = cached("frame", lambda: cutout(cv2.resize(real.rgb(real.frame_bgr), (fw, fh),
                                                            interpolation=cv2.INTER_AREA), 14))
    put(canvas, print_piece, t, L, home, "left", "frame", frame, tilt=-1.2)
    put(canvas, cached("lab1", lambda: note("the webcam: 640 × 480", 34, font=symbols_marker(34))),
        t, L, (home[0], 95), "top", "lab1", frame, t_in=0.4)
    bx, by, bs = real.BOX
    # Where the crop box sits on the print (top-left of the photo inside the white border)
    tlx, tly = home[0] - fw / 2, home[1] - fh / 2
    box_c = (tlx + (bx + bs / 2) * fs, tly + (by + bs / 2) * fs)
    if 2.0 <= t < 4.0:                       # the green box is laid on the print
        frame_piece = cached("boxframe", lambda: hollow_frame(int(bs * fs), 12, GREEN))
        place(canvas, frame_piece, box_c[0], box_c[1], "boxframe", frame)
    if t >= 4.0:
        # The crop jumps, in steps, from the box to the right side, shrinking as it goes
        p = min(1.0, (t - 4.0) / 2.0)
        size_now = int(bs * fs + (512 - bs * fs) * p)
        cx = box_c[0] + (1500 - box_c[0]) * p
        cy = box_c[1] + (480 - box_c[1]) * p
        if p < 1:
            crop_hi = real.rgb(real.frame_bgr[by:by + bs, bx:bx + bs])
            piece = cached(("crop", size_now), lambda: cutout(cv2.resize(crop_hi, (size_now, size_now),
                                                                          interpolation=cv2.INTER_AREA), 10))
            place(canvas, piece, cx, cy, "crop", frame, tilt=1.5 * p)
        else:
            pos = slide(t, L, (1500, 480), "right", 6.0, 0.01)
            if pos:
                piece = cached("crop128", lambda: cutout(cv2.resize(real.rgb(real.crop_bgr), (512, 512),
                                                                    interpolation=cv2.INTER_NEAREST), 10))
                place(canvas, piece, pos[0], pos[1], "crop", frame, tilt=1.5)
            put(canvas, cached("lab128", lambda: note("128 × 128 pixels", 40, font=symbols_marker(40))),
                t, L, (1500, 790), "bottom", "lab128", frame, t_in=6.0)
    caption(canvas, t, L, frame, [(0.3, "The safe's webcam looks down at the red square"),
                                  (2.0, "A saved box marks the red square"),
                                  (4.0, "The box is cut out and shrunk to 128 × 128"),
                                  (6.3, "This small picture is all the network ever sees")])


def symbols_marker(size):
    """Labels with a size in them ("640 x 480"): Noteworthy, which has a real times sign."""
    return hand(size)


def hollow_frame(inner, thick, colour):
    """A cut-paper frame (like a picture mount) with an empty middle."""
    size = inner + 2 * thick
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, size - 1, size - 1], outline=PAPER + (255,), width=thick + 4)
    d.rectangle([3, 3, size - 4, size - 4], outline=colour + (255,), width=thick - 2)
    return img


# ---- Scene 2: a photo is numbers -------------------------------------------------------------------

def s_numbers(canvas, t, frame, L):
    pr, pc = real.PATCH
    crop = real.rgb(real.crop_bgr)
    home = (W / 2, 470)
    if t < 6.3:
        # The zoom as a few replacement prints (each one a bigger enlargement), not a smooth zoom
        levels = [(0, 0, 128), (pc - 28, pr - 28, 64), (pc - 12, pr - 12, 32), (pc - 4, pr - 4, 16), (pc, pr, 8)]
        step = 0 if t < 1.5 else min(4, 1 + int((t - 1.5) / 0.6))
        vx, vy, vw = levels[step]
        vx, vy = max(0, min(vx, 128 - vw)), max(0, min(vy, 128 - vw))
        if step < 4 or t < 4.0:
            piece = cached(("zoom", step), lambda: cutout(real.view(crop, vx, vy, vw, out=640), 12))
        else:
            piece = cached("zoomnum", lambda: zoom_with_numbers(crop, pr, pc))
        put(canvas, piece, t, L, home, "left", "zoom", frame, tilt=-0.8, t_out=6.0)
        if step == 0:
            put(canvas, cached("hl", lambda: hollow_frame(40, 8, (240, 190, 40))), t, L,
                (home[0] - 320 + (pc + 4) * 5, home[1] - 320 + (pr + 4) * 5), "top", "hl", frame, t_in=0.6, t_out=1.5)
    else:
        scaled = t >= 8.7
        for k in range(3):
            piece = cached(("chan", k, scaled), lambda k=k: channel_sheet(k, scaled))
            put(canvas, piece, t, L, (380 + k * 580, 430), "bottom", ("chan", k), frame,
                t_in=6.5 + 0.35 * k, tilt=(k - 1) * 1.2)
        put(canvas, cached("total", lambda: note("128 × 128 pixels × 3 colours = 49,152 numbers", 46,
                                                  paper=NOTE_YELLOW)),
            t, L, (W / 2, 830), "right", "total", frame, t_in=7.6)
    caption(canvas, t, L, frame, [(0.3, "Zoom into a fingertip's edge"),
                                  (4.0, "Every pixel is 3 numbers: blue, green, red (0 to 255)"),
                                  (6.5, "So the photo is just three grids of numbers"),
                                  (8.7, "Divided by 255, they become 0 to 1: the network's input")])


def zoom_with_numbers(crop, pr, pc):
    """The 8x8 enlargement with each pixel's three numbers written on it."""
    img = Image.fromarray(np.ascontiguousarray(real.view(crop, pc, pr, 8, out=640))).convert("RGBA")
    d = ImageDraw.Draw(img)
    f = hand(24)
    cell = 80
    for i in range(9):
        d.line([i * cell, 0, i * cell, 640], fill=(20, 20, 20), width=2)
        d.line([0, i * cell, 640, i * cell], fill=(20, 20, 20), width=2)
    for r in range(8):
        for c in range(8):
            px = real.crop_bgr[pr + r, pc + c]
            for k in range(3):
                d.text(((c + 0.5) * cell, (r + 0.5) * cell - 22 + 22 * k), str(px[k]), font=f,
                       fill=pale(CHANNEL_INK[k], 0.45), anchor="mm", stroke_width=3, stroke_fill=(15, 15, 15))
    return cutout(img, 12)


def channel_sheet(k, scaled):
    """One colour's 8x8 numbers on pale tinted paper."""
    pr, pc = real.PATCH
    vals = real.crop_bgr[pr:pr + 8, pc:pc + 8, k].astype(float)
    if scaled:
        fmt = lambda v: "1.0" if v >= 255 else f"{v / 255:.2f}"[1:]
    else:
        fmt = lambda v: f"{int(v)}"
    body = grid_card(vals, fmt, 54, ink=CHANNEL_INK[k], paper=CHANNEL_PAPER[k], size=22)
    head = note(CHANNEL_NAMES[k], 40, paper=CHANNEL_PAPER[k], ink=CHANNEL_INK[k], tape=False)
    out = Image.new("RGBA", (body.width, body.height + head.height - 6), (0, 0, 0, 0))
    out.alpha_composite(head, ((body.width - head.width) // 2, 0))
    out.alpha_composite(body, (0, head.height - 6))
    return taped(out)


# ---- Scene 3: convolution ---------------------------------------------------------------------------

CLOSE = 24                                   # the close-up shows 24 x 24 photo pixels...
CELL = 20                                    # ...each 20 screen pixels: one hop of the window is clearly visible
SR, SC = real.SPOT
CR0 = int(min(max(SR - CLOSE // 2, 0), 128 - CLOSE))
CC0 = int(min(max(SC - 12, 0), 128 - CLOSE))
HOPS = 11                                    # hops along the spot's row before stopping on it


def window_position(t):
    """Which output pixel the cardboard window is over (row, col), and how much of the map is done."""
    if t < 0.4:
        return None, SR * 128 + SC - HOPS
    if t < 4.0:                              # one cell per hop, one hop every other pose (3 a second)
        hop = min(HOPS, int((t - 0.4) * 3))
        col = SC - HOPS + hop
        return (SR, col), SR * 128 + col + 1          # the cell under the window is now done
    if t < 11.0:
        return (SR, SC), SR * 128 + SC + 1
    # 11-13 s: the rest of the photo, in big jumps (a few rows each pose)
    p = min(1.0, (t - 11.0) / 2.0)
    pos = int(SR * 128 + SC + 1 + (128 * 128 - SR * 128 - SC - 1) * p)
    return divmod(min(pos, 128 * 128 - 1), 128), pos


def s_conv(canvas, t, frame, L):
    where, done = window_position(t)
    # Left: the close-up print with grid lines
    close_home = (290, 470)
    close_piece = cached("close", close_up)
    put(canvas, close_piece, t, L, close_home, "left", "close", frame, tilt=-0.7)
    put(canvas, cached("closelab", lambda: note("close-up around the spot", 30)), t, L,
        (close_home[0], 180), "top", "closelab", frame, t_in=0.2)
    # The cardboard window: jumps one cell at a time while it is inside the close-up
    if where is not None and slide(t, L, close_home, "left") == close_home:
        r, c = where
        if CR0 + 1 <= r <= CR0 + CLOSE - 2 and CC0 + 1 <= c <= CC0 + CLOSE - 2:
            x = close_home[0] - CLOSE * CELL / 2 + (c - CC0 + 0.5) * CELL
            y = close_home[1] - CLOSE * CELL / 2 + (r - CR0 + 0.5) * CELL
            place(canvas, cached("window", cardboard_window), x, y, "window", frame, wobble=0.6)
    # Right: the output, filled in as the window hops. Until 11 s it is a close-up of
    # the same 24 x 24 cells at the same size as the photo close-up, so each hop fills
    # one big, visible cell (outlined) right beside the window. After that the whole
    # map fills in, in big jumps.
    map_home = (1630, 470)
    if t < 11.0:
        piece = cached(("outclose", done), lambda: output_close(done))
        lab = cached("outlab", lambda: note("the output, same close-up", 30))
    else:
        piece = cached(("out", done), lambda: output_map(done))
        lab = cached("outlab2", lambda: note(f"filter {real.FILTER + 1}'s whole output map", 30))
    put(canvas, piece, t, L, map_home, "right", "outmap", frame, tilt=0.8)
    put(canvas, lab, t, L, (map_home[0], 180), "top", "outlab", frame, t_in=0.2)
    # Middle: the filter's real weights on three index cards, plus the bias
    for k in range(3):
        put(canvas, cached(("w", k), lambda k=k: weight_card(k)), t, L, (700 + k * 262, 300), "top",
            ("w", k), frame, t_in=0.3 + 0.15 * k, tilt=(k - 1) * 1.5)
    put(canvas, cached("bias", lambda: note(f"bias {real.B1:+.2f}", 32, paper=NOTE_YELLOW)), t, L,
        (960, 488), "top", "bias", frame, t_in=0.8)
    # 4-11 s: the multiply-and-add at the spot, on index cards
    if 4.0 <= t < 11.0:
        stage = "pixel" if t < 6.0 else "product"
        for k in range(3):
            piece = cached(("math", k, stage), lambda k=k, stage=stage: math_card(k, stage))
            put(canvas, piece, t, L, (700 + k * 262, 680), "bottom", ("math", k), frame,
                t_in=4.0 + 0.15 * k, tilt=(1 - k) * 1.0, t_out=10.6)
            if t >= 7.0:
                s = (real._patch[k] * real.W1[k]).sum()
                put(canvas, cached(("sum", k), lambda k=k, s=s: note(f"sum {s:+.2f}", 30, paper=PAPER,
                                                                      ink=CHANNEL_INK[k], tape=False)),
                    t, L, (700 + k * 262, 848), "bottom", ("sum", k), frame, t_in=7.0, t_out=10.6)
        if t >= 8.5:
            sums = [(real._patch[k] * real.W1[k]).sum() for k in range(3)]
            total = sum(sums) + real.B1
            text = f"{sums[0]:+.2f} {sums[1]:+.2f} {sums[2]:+.2f} + bias {real.B1:+.2f} = {total:+.2f}"
            put(canvas, cached("total3", lambda: note(text, 40, paper=NOTE_YELLOW)), t, L, (960, 912),
                "right", "total3", frame, t_in=8.5, t_out=10.6)
    caption(canvas, t, L, frame, [(0.3, "A filter is a small window of weights that hops over the photo"),
                                  (4.0, "At each spot: the 27 pixel numbers under it..."),
                                  (6.0, "...each times its weight..."),
                                  (7.0, "...added up..."),
                                  (8.5, "...plus a bias gives ONE output number"),
                                  (11.0, "Done at every spot, it paints a new picture: a feature map")])


def close_up():
    """The 24x24-pixel close-up around the spot, each pixel 20 screen pixels, with faint grid lines."""
    region = real.rgb(real.crop_bgr)[CR0:CR0 + CLOSE, CC0:CC0 + CLOSE]
    img = cv2.resize(region, (CLOSE * CELL, CLOSE * CELL), interpolation=cv2.INTER_NEAREST)
    img[::CELL, :] = img[::CELL, :] * 0.6
    img[:, ::CELL] = img[:, ::CELL] * 0.6
    return cutout(img, 12)


def cardboard_window():
    """A cardboard square with a 3x3-pixel hole: the filter."""
    hole = 3 * CELL
    rim = 16
    size = hole + 2 * rim
    rng = np.random.default_rng(3)
    board = np.clip(np.array(CARDBOARD, float) + rng.normal(0, 7, (size, size, 1)), 0, 255).astype(np.uint8)
    img = Image.fromarray(board).convert("RGBA")
    a = Image.new("L", (size, size), 255)
    ImageDraw.Draw(a).rectangle([rim, rim, rim + hole - 1, rim + hole - 1], fill=0)
    img.putalpha(a)
    ImageDraw.Draw(img).rectangle([rim - 2, rim - 2, rim + hole + 1, rim + hole + 1], outline=(110, 80, 50, 255), width=2)
    return img


def output_close(done):
    """The output close-up (same cells as the photo close-up): cells done so far coloured,
    the newest one outlined, the rest still blank card."""
    region = real.OUT_COLOURED[CR0:CR0 + CLOSE, CC0:CC0 + CLOSE].copy()
    rows, cols = np.mgrid[CR0:CR0 + CLOSE, CC0:CC0 + CLOSE]
    region[rows * 128 + cols >= done] = 225                   # not computed yet: blank
    img = cv2.resize(region, (CLOSE * CELL, CLOSE * CELL), interpolation=cv2.INTER_NEAREST)
    img[::CELL, :] = (img[::CELL, :] * 0.75).astype(np.uint8)
    img[:, ::CELL] = (img[:, ::CELL] * 0.75).astype(np.uint8)
    pic = Image.fromarray(img).convert("RGBA")
    last = done - 1                                           # the cell just filled
    r, c = divmod(last, 128)
    if CR0 <= r < CR0 + CLOSE and CC0 <= c < CC0 + CLOSE:
        x, y = (c - CC0) * CELL, (r - CR0) * CELL
        ImageDraw.Draw(pic).rectangle([x - 2, y - 2, x + CELL + 1, y + CELL + 1], outline=(240, 180, 30, 255), width=4)
    return cutout(pic, 12)


def output_map(done):
    """The output map (real colours), filled in up to `done` pixels, the rest left as blank card."""
    out = np.full((128, 128, 3), 225, np.uint8)
    flat = out.reshape(-1, 3)
    flat[:done] = real.OUT_COLOURED.reshape(-1, 3)[:done]
    return cutout(cv2.resize(out, (512, 512), interpolation=cv2.INTER_NEAREST), 12)


def weight_card(k):
    w = real.W1[k]
    body = grid_card(w, lambda v: f"{v:+.2f}", 76, colours=signed_colours(w, 0.6), size=21)
    head = note(CHANNEL_NAMES[k], 30, ink=CHANNEL_INK[k], tape=False, pad=(16, 6))
    out = Image.new("RGBA", (body.width, body.height + head.height - 4), (0, 0, 0, 0))
    out.alpha_composite(head, ((body.width - head.width) // 2, 0))
    out.alpha_composite(body, (0, head.height - 4))
    return taped(out)


def math_card(k, stage):
    """The 9 pixel numbers under the window (one colour), or each times its weight."""
    patch = real._patch[k]
    vals = patch if stage == "pixel" else patch * real.W1[k]
    fmt = (lambda v: f"{v:.2f}") if stage == "pixel" else (lambda v: f"{v:+.2f}")
    body = grid_card(vals, fmt, 76, size=21)
    head = note("pixel" if stage == "pixel" else "pixel × weight", 24, tape=False, pad=(12, 4), font=hand(24))
    out = Image.new("RGBA", (body.width, body.height + head.height - 4), (0, 0, 0, 0))
    out.alpha_composite(head, ((body.width - head.width) // 2, 0))
    out.alpha_composite(body, (0, head.height - 4))
    return out


# ---- Scene 4: ReLU ------------------------------------------------------------------------------------

def s_relu(canvas, t, frame, L):
    # The red parts fade to white in 4 replacement prints (not a smooth fade)
    step = 0 if t < 1.8 else min(4, 1 + int((t - 1.8) / 0.6))
    f = step / 4
    piece = cached(("relu", step), lambda: cutout(cv2.resize(
        real.diverging(np.where(real.out_pre < 0, real.out_pre * (1 - f), real.out_pre), real.VMAX).astype(np.uint8),
        (620, 620), interpolation=cv2.INTER_NEAREST), 12))
    put(canvas, piece, t, L, (520, 480), "left", "relumap", frame, tilt=-1.0)
    put(canvas, cached("legend", lambda: note("red = negative\nblue = positive", 40)), t, L,
        (1350, 230), "top", "legend", frame, t_in=0.3, tilt=1.5)
    if t >= 1.0:
        put(canvas, cached("rule", lambda: note("ReLU: keep positives,\nnegatives become 0", 42, paper=NOTE_YELLOW)),
            t, L, (1350, 470), "right", "rule", frame, t_in=1.0, tilt=-1.0)
    neg, pos = float(real.out_pre.min()), float(real.out_pre.max())
    if t >= 1.8:
        left = cached(("neg", step == 4), lambda: arrow_card(f"{neg:+.2f}", "0" if step == 4 else "?",
                                                               RED if step < 4 else INK))
        put(canvas, left, t, L, (1350, 680), "right", "negcard", frame, t_in=1.8, tilt=1.2)
        put(canvas, cached("poscard", lambda: arrow_card(f"{pos:+.2f}", f"{pos:+.2f}", BLUE)),
            t, L, (1350, 810), "right", "poscard", frame, t_in=2.2, tilt=-0.8)
    caption(canvas, t, L, frame, [(0.3, f"{np.mean(real.out_pre < 0):.0%} of this map came out negative"),
                                  (1.8, "ReLU turns every negative number into 0"),
                                  (4.3, "Only the \"I found my pattern here\" signals go on")])


def arrow_card(left, right, ink):
    """An index card: "left -> right" in handwriting, with the arrow drawn by hand (no font has a
    hand-written arrow)."""
    f = hand(46)
    img = Image.new("RGBA", (420, 90), PAPER + (255,))
    d = ImageDraw.Draw(img)
    d.text((95, 45), left, font=f, fill=ink, anchor="mm")
    d.line([175, 47, 255, 47], fill=INK, width=5)
    d.polygon([(255, 35), (278, 47), (255, 59)], fill=INK)
    d.text((345, 45), right, font=f, fill=ink, anchor="mm")
    return taped(img)


# ---- Scene 5: pooling ---------------------------------------------------------------------------------

def s_pool(canvas, t, frame, L):
    r0, c0 = real.POOL_AT
    region = real.out_relu[r0:r0 + 8, c0:c0 + 8]
    top = float(np.percentile(real.out_relu, 99))
    cell = 62
    grid_home = (360, 500)
    put(canvas, cached("poolgrid", lambda: grid_card(region, lambda v: f"{v:.2f}", cell,
                                                     colours=signed_colours(region, top), size=19)),
        t, L, grid_home, "left", "poolgrid", frame, tilt=-0.8)
    put(canvas, cached("poollab", lambda: note("an 8 × 8 piece of the map", 30)), t, L,
        (grid_home[0], 185), "top", "poollab", frame, t_in=0.2)
    # The yellow 2x2 frame jumps from block to block; the result card fills one number at a time
    n = 0 if t < 0.6 else min(16, int((t - 0.6) / 0.25) + 1)
    if 0.6 <= t < 4.8 and n <= 16:
        b = min(n, 16) - 1
        br, bc = divmod(b, 4)
        x = grid_home[0] - 4 * cell + (bc * 2 + 1) * cell
        y = grid_home[1] - 4 * cell + (br * 2 + 1) * cell
        place(canvas, cached("pool2x2", lambda: hollow_frame(2 * cell, 8, (240, 190, 40))), x, y, "pool2x2", frame, wobble=0.6)
    res = np.array([[region[br * 2:br * 2 + 2, bc * 2:bc * 2 + 2].max() for bc in range(4)] for br in range(4)])
    put(canvas, cached(("poolres", n), lambda: pooled_card(res, n, top, cell)), t, L, (900, 560), "bottom",
        "poolres", frame, t_in=0.4, tilt=1.0)
    put(canvas, cached("poolres_lab", lambda: note("keep the biggest", 30)), t, L, (900, 330), "top",
        "poolres_lab", frame, t_in=0.4)
    if t >= 5.0:
        put(canvas, cached("big128", lambda: cutout(cv2.resize(real.diverging(real.out_relu, top).astype(np.uint8),
                                                               (384, 384), interpolation=cv2.INTER_NEAREST), 10)),
            t, L, (1390, 470), "right", "big128", frame, t_in=5.0, tilt=-1.0)
        put(canvas, cached("small64", lambda: cutout(cv2.resize(real.diverging(real.pooled1, top).astype(np.uint8),
                                                                (192, 192), interpolation=cv2.INTER_NEAREST), 8)),
            t, L, (1740, 470), "right", "small64", frame, t_in=5.3, tilt=1.5)
        put(canvas, cached("l128", lambda: note("128 × 128", 32, tape=False)), t, L, (1390, 720), "bottom", "l128", frame, t_in=5.6)
        put(canvas, cached("l64", lambda: note("64 × 64", 32, tape=False)), t, L, (1740, 640), "bottom", "l64", frame, t_in=5.8)
    caption(canvas, t, L, frame, [(0.3, "Max pooling: look at each 2 × 2 block..."),
                                  (2.0, "...and keep only the biggest number"),
                                  (5.0, "The picture halves: 128 × 128 becomes 64 × 64"),
                                  (6.5, "Less to compute, and a finger can move a little")])


def pooled_card(res, n, top, cell):
    """The 4x4 result card with the first n numbers written in."""
    img = Image.new("RGBA", (4 * cell, 4 * cell), PAPER + (255,))
    d = ImageDraw.Draw(img)
    f = hand(19)
    for b in range(16):
        br, bc = divmod(b, 4)
        box = [bc * cell, br * cell, (bc + 1) * cell, (br + 1) * cell]
        if b < n:
            d.rectangle(box, fill=tuple(int(v) for v in signed_colours(np.array([[res[br, bc]]]), top)[0, 0]))
            d.text(((bc + 0.5) * cell, (br + 0.5) * cell), f"{res[br, bc]:.2f}", font=f, fill=INK, anchor="mm")
        d.rectangle(box, outline=(170, 175, 190), width=1)
    return cutout(img, 10)


# ---- Scene 6: going deeper ------------------------------------------------------------------------------

def s_deeper(canvas, t, frame, L):
    groups = [  # (maps, cols, tile, gap, left x, top y, title, meaning, arrives)
        (real.maps[0], 4, 132, 14, 70, 330, "layer 1: 8 maps, 128 × 128", "edges and colours", 0.3),
        (real.maps[1], 4, 80, 12, 760, 300, "layer 2: 16 maps, 64 × 64", "finger shapes", 3.3),
        (real.maps[2], 8, 50, 9, 1270, 350, "layer 3: 32 maps, 32 × 32", "fingers and gaps", 6.3),
    ]
    for g, (stack, cols, tile, gap, x0, y0, title, meaning, at) in enumerate(groups):
        if t < at:
            continue
        rows = (len(stack) + cols - 1) // cols
        for i, m in enumerate(stack):
            r, c = divmod(i, cols)
            cx = x0 + c * (tile + gap) + tile / 2
            cy = y0 + r * (tile + gap) + tile / 2
            piece = cached(("tile", g, i), lambda m=m, tile=tile: cutout(
                cv2.resize(real.magma(m), (tile, tile), interpolation=cv2.INTER_NEAREST), 5))
            put(canvas, piece, t, L, (cx, cy), "bottom", ("tile", g, i), frame, t_in=at + 0.03 * (i % cols),
                tilt=((i * 37) % 7 - 3) * 0.5, dur=0.5)
        gw = cols * (tile + gap) - gap
        put(canvas, cached(("gt", g), lambda title=title: note(title, 30)), t, L, (x0 + gw / 2, y0 - 70), "top",
            ("gt", g), frame, t_in=at)
        put(canvas, cached(("gm", g), lambda meaning=meaning: note(meaning, 34, paper=NOTE_YELLOW)), t, L,
            (x0 + gw / 2, y0 + rows * (tile + gap) + 50), "bottom", ("gm", g), frame, t_in=at + 0.3)
    for g, (ax, at) in enumerate(((700, 3.3), (1220, 6.3))):
        put(canvas, cached("arrow", paper_arrow), t, L, (ax, 500), "top", ("arrow", g), frame, t_in=at)
    caption(canvas, t, L, frame, [(0.3, "Layer 1: 8 filters find simple edges and colours"),
                                  (3.3, "Layer 2: 16 filters combine them into finger shapes"),
                                  (6.3, "Layer 3: 32 filters see whole fingers and the gaps between them"),
                                  (9.0, "Each layer: convolution, ReLU, pooling, smaller and smarter")])


def paper_arrow():
    """A small arrow cut out of paper."""
    img = Image.new("RGBA", (90, 60), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([(4, 20), (54, 20), (54, 4), (86, 30), (54, 56), (54, 40), (4, 40)],
                                fill=PAPER + (255,), outline=INK + (255,), width=3)
    return img


# ---- Scene 7: the answer --------------------------------------------------------------------------------

def s_answer(canvas, t, frame, L):
    sheet = cached("pooled3", lambda: pooled_sheet())
    put(canvas, sheet, t, L, (280, 470), "left", "pooled3", frame, tilt=-1.2)
    put(canvas, cached("p3lab", lambda: note("32 maps × 16 × 16\n= 8,192 numbers", 36, paper=NOTE_YELLOW)),
        t, L, (280, 750), "bottom", "p3lab", frame, t_in=0.4, tilt=1.5)
    if t >= 1.5:
        put(canvas, cached("arrowA", paper_arrow), t, L, (570, 470), "top", "arrowA", frame, t_in=1.5)
        put(canvas, cached("final", lambda: note("final layer\n8,192 × 6 weights", 34)), t, L, (760, 470), "top",
            "final", frame, t_in=1.5, tilt=-1.5)
        put(canvas, cached("arrowB", paper_arrow), t, L, (950, 470), "top", "arrowB", frame, t_in=1.7)
    # The six paper strips grow in steps (8 steps), using the real confidences
    win = int(real.probs.argmax())
    g = 0 if t < 2.0 else min(8, int((t - 2.0) / 0.375) + 1) / 8
    bx, base, bw, bh = 1080, 820, 112, 540
    for i, p in enumerate(real.probs):
        h = max(4, int(bh * p * g))
        green = i == win and t >= 5.3
        strip = cached(("strip", i, h, green), lambda h=h, green=green: paper_strip(bw, h, GREEN if green else (150, 155, 165)))
        cx = bx + i * (bw + 26) + bw / 2
        if t >= 2.0:
            pos = slide(t, L, (cx, base - h / 2), "bottom", 2.0, 0.01)
            if pos:
                place(canvas, strip, pos[0], pos[1], ("strip", i), frame, wobble=0.5)
                lab = cached(("pct", i, round(p * g, 2)), lambda v=p * g: note(f"{v:.0%}" if v >= 0.005 else "0%", 26,
                                                                               tape=False, pad=(10, 4)))
                place(canvas, lab, cx, base - h - 34, ("pct", i), frame)
        put(canvas, cached(("digit", i), lambda i=i: note(str(i), 40, tape=False, pad=(18, 4))), t, L,
            (cx, base + 45), "bottom", ("digit", i), frame, t_in=1.8)
    if t >= 5.3:
        put(canvas, cached("win", lambda: note(f"{win} fingers ({real.probs[win]:.0%} sure)", 60, paper=NOTE_YELLOW,
                                               ink=GREEN)),
            t, L, (1450, 160), "top", "win", frame, t_in=5.3, tilt=-2.0)
    caption(canvas, t, L, frame, [(0.3, "Everything left: 8,192 numbers"),
                                  (1.5, "The final layer weighs them all into 6 scores, one per answer"),
                                  (5.3, "The biggest wins: two fingers")])


def pooled_sheet():
    tiles = [cv2.resize(real.magma(m), (40, 40), interpolation=cv2.INTER_NEAREST) for m in real.pooled3]
    sheet = np.full((4 * 44 - 4, 8 * 44 - 4, 3), 245, np.uint8)
    for i, tl in enumerate(tiles):
        r, c = divmod(i, 8)
        sheet[r * 44:r * 44 + 40, c * 44:c * 44 + 40] = tl
    return cutout(sheet, 10)


def paper_strip(w, h, colour):
    img = Image.new("RGBA", (w, h), colour + (255,))
    rng = np.random.default_rng(h)
    noise = Image.fromarray((rng.normal(0, 6, (h, w)) + 128).clip(0, 255).astype(np.uint8))
    img = Image.composite(img, img, noise)          # (keeps the strip simple; the border makes it paper)
    return cutout(img, 5)


# ---- Bonus scene: how it learned -------------------------------------------------------------------------

GRAPH = (1500, 680)                 # the graph card's inside size


def s_training(canvas, t, frame, L):
    n_ep = len(real.EPOCHS)
    upto = 1 if t < 0.6 else min(n_ep, 1 + int((t - 0.6) / 6.2 * (n_ep - 1)))
    piece = cached(("graph", upto), lambda: graph_card(upto))
    home = (W / 2, 490)
    put(canvas, piece, t, L, home, "bottom", "graph", frame, tilt=-0.6)
    if slide(t, L, home, "bottom") == home:
        x, y = graph_point(upto, real.TRAIN_LOSS[upto - 1])
        hop = 26 if (int(t * 6) % 2 == 1 and upto < n_ep) else 0        # every other pose, the ball is mid-hop
        place(canvas, cached("ball", paper_ball), home[0] - GRAPH[0] / 2 + x, home[1] - GRAPH[1] / 2 + y - 22 - hop,
              "ball", frame, wobble=1.5)
        if upto >= real.BEST_EPOCH:
            bx, _ = graph_point(real.BEST_EPOCH, 0)
            place(canvas, cached("flag", lambda: note(f"best: epoch {real.BEST_EPOCH}, saved", 26, paper=NOTE_YELLOW,
                                                      ink=GREEN, tape=False)),
                  home[0] - GRAPH[0] / 2 + bx, home[1] - GRAPH[1] / 2 + 190, "flag", frame)   # below the legend
    caption(canvas, t, L, frame, [(0.3, f"Where the weights come from: all {real.N_PARAMS:,} started random"),
                                  (2.5, "Each pass, every weight is nudged downhill: a little less wrong"),
                                  (5.5, "The paper ball follows the real training run of this network")])


def graph_point(epoch, loss):
    top = float(max(real.TRAIN_LOSS.max(), real.VAL_LOSS.max())) * 1.05
    x0, x1, y0, y1 = 110, GRAPH[0] - 40, 50, GRAPH[1] - 80
    return (x0 + (epoch - 1) / (len(real.EPOCHS) - 1) * (x1 - x0), y1 - loss / top * (y1 - y0))


def graph_card(upto):
    """The loss graph drawn in marker on a big card, up to epoch `upto`."""
    img = Image.new("RGBA", GRAPH, PAPER + (255,))
    d = ImageDraw.Draw(img)
    x0, y1 = 110, GRAPH[1] - 80
    d.line([x0, 40, x0, y1, GRAPH[0] - 30, y1], fill=INK, width=4)
    d.text((x0 + 10, 22), "loss (how wrong)", font=marker(30), fill=INK, anchor="lm")
    d.text((GRAPH[0] / 2, GRAPH[1] - 30), "epoch: one pass over the 816 training photos", font=marker(30), fill=INK, anchor="mm")
    for e in (1, 20, 40, 60, 80):
        x, _ = graph_point(e, 0)
        d.text((x, y1 + 22), str(e), font=hand(24), fill=INK, anchor="mm")
    pts = [graph_point(e, l) for e, l in zip(real.EPOCHS[:upto], real.TRAIN_LOSS[:upto])]
    vpts = [graph_point(e, l) for e, l in zip(real.EPOCHS[:upto], real.VAL_LOSS[:upto])]
    if len(vpts) > 1:
        d.line(vpts, fill=(205, 150, 150), width=3, joint="curve")
    if len(pts) > 1:
        d.line(pts, fill=BLUE, width=6, joint="curve")
    d.text((GRAPH[0] - 40, 40), "training photos", font=marker(28), fill=BLUE, anchor="rm")
    d.text((GRAPH[0] - 40, 78), "validation photos (never learned from)", font=marker(26), fill=(190, 120, 120), anchor="rm")
    return cutout(img, 14)


def paper_ball():
    """A crumpled paper ball: a white circle with a few grey crease lines."""
    s = 52
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, s - 3, s - 3], fill=(248, 247, 240, 255), outline=(150, 150, 150, 255), width=2)
    rng = np.random.default_rng(7)
    for _ in range(6):
        a, b = rng.uniform(10, s - 10, 2), rng.uniform(10, s - 10, 2)
        d.line([tuple(a), tuple(b)], fill=(170, 170, 170, 255), width=2)
    return img


# ---- Ending ------------------------------------------------------------------------------------------------

def s_end(canvas, t, frame, L):
    put(canvas, cached("safe", safe_print), t, L, (520, 500), "left", "safe", frame, tilt=-3.0)
    for i in range(3):                                                  # three paper dots, no digits
        cx = 1180 + i * 170
        put(canvas, cached("dot_empty", lambda: dot(False)), t, L, (cx, 330), "top", ("dote", i), frame, t_in=0.2)
        if t >= 0.6 + i * 0.7:
            place(canvas, cached("dot_full", lambda: dot(True)), cx, 330, ("dotf", i), frame)
    if t >= 2.8:
        put(canvas, cached("unlocked", unlocked_note), t, L, (1350, 600), "right", "unlocked", frame,
            t_in=2.8, tilt=-2.5, dur=0.5)
    caption(canvas, t, L, frame, [(0.3, "Three digits, each counted by the network..."),
                                  (2.8, "...and the latch swings open")])


def safe_print():
    """The real photo of the safe as a paper print (a placeholder card if the photo isn't there yet)."""
    if SAFE_PHOTO.exists():
        img = Image.open(SAFE_PHOTO).convert("RGB")
        img.thumbnail((620, 620))
        return cutout(np.asarray(img), 16)
    img = Image.new("RGBA", (560, 420), (230, 225, 215, 255))
    ImageDraw.Draw(img).text((280, 210), "(photo of the safe)", font=marker(40), fill=INK, anchor="mm")
    return cutout(img, 16)


def dot(filled):
    s = 92
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([3, 3, s - 4, s - 4], fill=(INK if filled else PAPER) + (255,), outline=INK + (255,), width=5)
    return img


def unlocked_note():
    img = Image.new("RGBA", (720, 220), PAPER + (255,))
    d = ImageDraw.Draw(img)
    g = GREEN + (255,)
    # an open padlock drawn in marker
    d.rounded_rectangle([40, 100, 150, 190], 12, fill=g)
    d.arc([88, 20, 178, 130], 180, 360, fill=g, width=14)
    d.line([171, 75, 171, 100], fill=g, width=14)
    d.text((450, 112), "UNLOCKED", font=marker(100), fill=GREEN, anchor="mm")
    return taped(img)


# ---- Putting it together --------------------------------------------------------------------------------------

STYLE = {"The photo": s_photo, "A photo is numbers": s_numbers, "Convolution": s_conv, "ReLU": s_relu,
         "Pooling": s_pool, "Going deeper": s_deeper, "The answer": s_answer, "How it learned": s_training,
         "Unlocked": s_end}


def render(parts, writer, stills=None):
    """parts: [(drawing function, seconds, first second to draw)]. Writes 12 fps frames, each pose held 2 frames."""
    frame = 0
    for draw, length, start in parts:
        n = int(round(length * FPS))
        for i in range(n):
            pose = (i // HOLD) * HOLD                       # the pose changes every 2 frames
            t = start + pose / FPS
            canvas = desk(frame)
            draw(canvas, t, frame, start + length)
            out = np.asarray(canvas.convert("RGB"))
            writer.write(cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
            if stills is not None and i in stills:
                stills[i] = out
            frame += 1
    return frame


def contact_sheet():
    """contact_sheet.png: frames taken from the finished MP4 itself (so it shows what will really
    play), two per scene plus a title card, each labelled with its time, for reviewing."""
    cap = cv2.VideoCapture(str(OUT_VIDEO))
    shots, clock = [], 0.0
    for title, _s, _d, secs in real.SCENES:
        c0 = clock + real.TITLE_S
        if not shots:
            shots.append((clock + 1.0, "title card"))
        for frac in (0.35, 0.85):
            sec = c0 + secs * frac
            shots.append((sec, f"{title} ({int(sec // 60)}:{sec % 60:04.1f})"))
        clock = c0 + secs
    tw, th, lab = 480, 270, 30
    sheet = np.full((5 * (th + lab), 4 * tw, 3), 30, np.uint8)
    for i, (sec, name) in enumerate(shots[:20]):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(sec * FPS)))
        ok, f = cap.read()
        r, c = divmod(i, 4)
        y, x = r * (th + lab), c * tw
        sheet[y + lab:y + lab + th, x:x + tw] = cv2.resize(f, (tw, th), interpolation=cv2.INTER_AREA)
        cv2.putText(sheet, name, (x + 8, y + 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.imwrite(str(HERE / "contact_sheet.png"), sheet)
    print("Saved contact_sheet.png")


def main():
    if "--sheet" in sys.argv:                              # only remake the contact sheet
        contact_sheet()
        return
    writer_path = OUT_VIDEO
    if "--test" in sys.argv:                               # a 5-second test of the convolution scene
        writer_path = HERE / "test_conv.mp4"
        writer = cv2.VideoWriter(str(writer_path), cv2.VideoWriter_fourcc(*"avc1"), FPS, (W, H))
        stills = {int(1.0 * FPS): None, int(4.5 * FPS): None}     # mid-hops, and the index cards
        render([(lambda c, t, f, L: s_conv(c, t, f, 14.0), 5.0, 2.0)], writer, stills)
        writer.release()
        for k, img in stills.items():
            Image.fromarray(img).save(HERE / f"test_conv_still_{k}.png")
        print(f"Saved {writer_path.name} and stills")
        return
    writer = cv2.VideoWriter(str(writer_path), cv2.VideoWriter_fourcc(*"avc1"), FPS, (W, H))
    parts, clock, times = [], 0.0, []
    for title, subtitle, _draw, seconds in real.SCENES:
        times.append((clock, title))
        parts.append((title_card(title, subtitle), real.TITLE_S, 0.0))
        parts.append((STYLE[title], seconds, 0.0))
        clock += real.TITLE_S + seconds
    frames = render(parts, writer)
    writer.release()
    print(f"Saved {writer_path.name}: {frames} frames = {frames / FPS:.1f} s")
    contact_sheet()


if __name__ == "__main__":
    main()
