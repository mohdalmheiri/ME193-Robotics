# AR drawing for game.py: a perspective ping-pong table, the ball's flight with a
# bounce and shadow, and the virtual paddle. Drawing only - no game rules here.
#
# Table coordinates: u = across the table (0 = left edge, 1 = right edge),
# d = depth (0 = far end, 1 = near end, at the bottom of the screen),
# z = height above the table, in table widths (a real table is ~1.5 m wide).
import math

import cv2
import numpy as np

# Table on screen (normalized): far end narrow near the top center, near end wide at the bottom
TABLE_FAR = (0.34, 0.66, 0.46)    # left x, right x, y
TABLE_NEAR = (0.03, 0.97, 0.99)
TABLE_ALPHA = 0.27                # 0 = invisible, 1 = solid
TABLE_COLOR = (150, 70, 20)       # BGR: ping-pong blue
LINE_COLOR = (255, 255, 255)
NET_HEIGHT = 0.10                 # table widths (15 cm on a 1.5 m wide table)

# Ball flight (fractions of the flight time / table)
BOUNCE_D_RANGE = (0.55, 0.85)     # bounce depth limits: always on your half (the net is at 0.5)
MIN_BOUNCE_S = 0.15               # the bounce is never earlier than this fraction of the flight
START_Z = 0.12                    # height when it leaves the far end
ARC_IN = 0.22                     # extra height of the arc before the bounce
ARC_OUT = 0.18                    # extra height of the arc after the bounce
BALL_SIZE = 0.049                 # ball radius as a fraction of the table width at its depth
BALL_COLOR = (40, 150, 255)       # BGR orange
MAX_D = 1.35                      # stop extrapolating past you beyond this depth
LEAVE_PADDLE_D = 0.6              # an incoming ball leaves the bot's paddle and lines up with your
                                  # target by this fraction of the way to its bounce

# Your return shot, flying to the bot's end
RET_BOUNCE_S = 0.6                # bounces on the bot's half at this fraction of the flight...
RET_BOUNCE_D = 0.3                # ...at this depth
RET_ARC = 0.22                    # extra height of the arcs
BOT_PADDLE_Z = 0.15               # the bot hits the ball at this height above its end of the table
MIN_D = -0.45                     # a ball the bot missed flies on past its end, up to here


def lerp(a, b, q):
    return a + (b - a) * q


def blend(frame, alpha, box, draw):
    """Run draw(img, ox, oy) on a copy of the box region and mix it back in with alpha."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = max(0, int(box[0])), max(0, int(box[1])), min(w, int(box[2])), min(h, int(box[3]))
    if x1 <= x0 or y1 <= y0:
        return
    roi = frame[y0:y1, x0:x1]
    layer = roi.copy()
    draw(layer, x0, y0)
    cv2.addWeighted(layer, alpha, roi, 1 - alpha, 0, roi)


class TableView:
    def __init__(self, w, h):
        self.w, self.h = w, h
        fl, fr, fy = TABLE_FAR
        nl, nr, ny = TABLE_NEAR
        src = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
        dst = np.float32([[fl * w, fy * h], [fr * w, fy * h], [nr * w, ny * h], [nl * w, ny * h]])
        self.H = cv2.getPerspectiveTransform(src, dst)
        self.corners = dst.astype(np.int32)
        self.near_left, self.near_right, self.near_y = nl * w, nr * w, ny * h

        # the table layer never changes, so build it once: blue surface, white lines, net
        y0 = int(fy * h) - int(NET_HEIGHT * self.width_at(0.5)) - 4
        self.roi = (0, max(0, y0), w, h)
        rh = h - self.roi[1]
        self.layer = np.zeros((rh, w, 3), np.uint8)
        self.mask = np.zeros((rh, w), np.uint8)
        off = np.array([0, self.roi[1]])
        cv2.fillConvexPoly(self.layer, self.corners - off, TABLE_COLOR)
        cv2.fillConvexPoly(self.mask, self.corners - off, 255)
        cv2.polylines(self.layer, [self.corners - off], True, LINE_COLOR, max(2, int(h / 240)), cv2.LINE_AA)
        a, b = self.screen(0.5, 0), self.screen(0.5, 1)
        cv2.line(self.layer, tuple(int(v) for v in a - off), tuple(int(v) for v in b - off),
                 LINE_COLOR, max(1, int(h / 480)), cv2.LINE_AA)
        # net: a strip standing up at the middle of the table
        l, r = self.screen(-0.03, 0.5), self.screen(1.03, 0.5)
        nh = NET_HEIGHT * self.width_at(0.5)
        net = np.int32([l - off, r - off, r - off - [0, nh], l - off - [0, nh]])
        cv2.fillConvexPoly(self.layer, net, (200, 200, 200))
        cv2.fillConvexPoly(self.mask, net, 255)
        cv2.line(self.layer, tuple(net[3]), tuple(net[2]), LINE_COLOR, max(2, int(h / 240)), cv2.LINE_AA)

    def screen(self, u, d):
        """Pixel position of table point (u, d)."""
        p = self.H @ np.array([u, d, 1.0])
        return p[:2] / p[2]

    def width_at(self, d):
        """Table width in pixels at depth d (= pixels per table width at that distance)."""
        return float(np.linalg.norm(self.screen(1, d) - self.screen(0, d)))

    def project(self, u, d, z):
        """(x, y) of a point z table widths above (u, d), the shadow (x, y) under it, and the pixel scale."""
        sx, sy = self.screen(u, d)
        scale = self.width_at(d)
        return (sx, sy - z * scale), (sx, sy), scale

    def u_for_x(self, x, d):
        """Table u at depth d that appears at screen x (pixels), kept on the table (0..1)."""
        H = self.H
        u = (x * (H[2, 1] * d + H[2, 2]) - H[0, 1] * d - H[0, 2]) / (H[0, 0] - x * H[2, 0])
        return min(max(u, 0.0), 1.0)

    def target_to_table(self, x, y):
        """Table coordinates (u, z) at the near end (d = 1) that land on screen point (x, y), normalized."""
        u = (x * self.w - self.near_left) / (self.near_right - self.near_left)
        z = (self.near_y - y * self.h) / (self.near_right - self.near_left)
        return u, max(0.0, z)

    def draw_table(self, frame):
        x0, y0, x1, y1 = self.roi
        roi = frame[y0:y1, x0:x1]
        mixed = cv2.addWeighted(self.layer, TABLE_ALPHA, roi, 1 - TABLE_ALPHA, 0)
        cv2.copyTo(mixed, self.mask, roi)


def bounce_plan(flight, early_window):
    """(bounce_s, bounce_d): when (fraction of the flight) and where (depth) the ball bounces.

    The bounce happens when the hit window opens (arrival - early_window), unless that
    is earlier than MIN_BOUNCE_S of the flight. The depth follows the timing, kept on your half.
    """
    bounce_s = max(MIN_BOUNCE_S, 1 - early_window / flight)
    return bounce_s, min(max(bounce_s, BOUNCE_D_RANGE[0]), BOUNCE_D_RANGE[1])


def ball_state(ball, now, table):
    """Ball's table position (u, d, z) at time `now`. Lands exactly on the target at ball["arrive"].

    It travels straight down the table in line with the target: at every depth, u is
    chosen so the ball's screen x equals the target's x (as close as the table edge allows).
    Before the bounce it arcs from the far end down to the table at ball["bounce_d"];
    after it rises into the target (d = 1). Past arrival it keeps going.
    """
    s = (now - ball["start"]) / (ball["arrive"] - ball["start"])
    sb, db = ball["bounce_s"], ball["bounce_d"]
    if s <= sb:
        q = max(0.0, s / sb)
        d = db * q
        z = (1 - q) * START_Z + ARC_IN * 4 * q * (1 - q)
    else:
        q = (s - sb) / (1 - sb)
        d = db + (1 - db) * q
        z = max(0.0, q * ball["zt"] + ARC_OUT * 4 * q * (1 - q))
    d = min(d, MAX_D)
    u = table.u_for_x(ball["x"] * table.w, d)
    if "u0" in ball:   # leaves from the bot's paddle, then lines up with your target
        q = min(1.0, d / (LEAVE_PADDLE_D * db))
        q = q * q * (3 - 2 * q)
        u = lerp(ball["u0"], u, q)
    return u, d, z


def return_state(ret, now):
    """Your return shot's table position (u, d, z): from where you hit it, a bounce on the
    bot's half, then up to the bot's paddle height at ret["land"] exactly at ret["arrive"].
    Past arrival (the bot missed) it keeps flying beyond the far end."""
    s = (now - ret["start"]) / (ret["arrive"] - ret["start"])
    u1, d1, z1 = ret["from"]
    u = lerp(u1, ret["land"], s)
    if s <= RET_BOUNCE_S:
        q = max(0.0, s / RET_BOUNCE_S)
        d = lerp(d1, RET_BOUNCE_D, q)
        z = lerp(z1, 0.0, q) + RET_ARC * 4 * q * (1 - q)
    else:
        q = (s - RET_BOUNCE_S) / (1 - RET_BOUNCE_S)
        d = lerp(RET_BOUNCE_D, 0.0, q)
        z = max(0.0, lerp(0.0, BOT_PADDLE_Z, q) + RET_ARC * 4 * q * (1 - q))
    return u, max(d, MIN_D), z


def draw_robot(frame, table, x, color, now):
    """An original cartoon robot standing behind the far end, holding a blue paddle at x."""
    s = table.width_at(0.0)                       # pixels per table width at the far end
    (px, py), (fx, fy), _ = table.project(x, 0.0, BOT_PADDLE_Z)
    bob = 0.006 * s * math.sin(now * 6)           # idle bobbing
    cx = int(fx)
    base = int(fy - 0.02 * s + bob)
    bw, bh, hw, hh = 0.2 * s, 0.24 * s, 0.17 * s, 0.13 * s
    body_top = int(base - bh)
    head_top = int(body_top - 0.03 * s - hh)
    dark = tuple(int(c * 0.55) for c in color)
    lw = max(1, int(s / 150))
    # antenna
    cv2.line(frame, (cx, head_top), (cx, int(head_top - 0.06 * s)), (200, 200, 200), lw, cv2.LINE_AA)
    cv2.circle(frame, (cx, int(head_top - 0.06 * s)), max(2, int(0.015 * s)), (0, 0, 255), -1, cv2.LINE_AA)
    # head with two glowing eyes
    cv2.rectangle(frame, (int(cx - hw / 2), head_top), (int(cx + hw / 2), int(head_top + hh)), (200, 200, 200), -1)
    cv2.rectangle(frame, (int(cx - hw / 2), head_top), (int(cx + hw / 2), int(head_top + hh)), dark, lw)
    for ex in (-0.045, 0.045):
        cv2.circle(frame, (int(cx + ex * s), int(head_top + hh * 0.45)), max(2, int(0.022 * s)), color, -1, cv2.LINE_AA)
    cv2.line(frame, (int(cx - 0.035 * s), int(head_top + hh * 0.78)), (int(cx + 0.035 * s), int(head_top + hh * 0.78)),
             dark, lw, cv2.LINE_AA)
    # neck + body in the bot's color
    cv2.rectangle(frame, (int(cx - 0.02 * s), int(head_top + hh)), (int(cx + 0.02 * s), body_top), (150, 150, 150), -1)
    cv2.rectangle(frame, (int(cx - bw / 2), body_top), (int(cx + bw / 2), base), color, -1)
    cv2.rectangle(frame, (int(cx - bw / 2), body_top), (int(cx + bw / 2), base), dark, lw)
    cv2.circle(frame, (cx, int(body_top + bh * 0.4)), max(2, int(0.03 * s)), (255, 255, 255), -1, cv2.LINE_AA)
    # arm out to the paddle (in front of the body), paddle = blue disc with a handle
    r = max(4, int(0.07 * s))
    cv2.line(frame, (int(cx + bw / 2), int(body_top + bh * 0.3)), (int(px), int(py + r)), (150, 150, 150),
             max(2, int(0.02 * s)), cv2.LINE_AA)
    cv2.line(frame, (int(px), int(py)), (int(px), int(py + 1.6 * r)), (60, 110, 160), max(2, int(0.025 * s)), cv2.LINE_AA)
    cv2.circle(frame, (int(px), int(py)), r, (200, 90, 20), -1, cv2.LINE_AA)
    cv2.circle(frame, (int(px), int(py)), r, (120, 50, 10), lw, cv2.LINE_AA)
    return int(cx - 0.6 * s), int(head_top - 0.1 * s), int(cx + 0.6 * s), base   # rough box (for occlusion)


def draw_shadow(frame, table, u, d, z, alpha=1.0):
    """Shadow on the table under the ball: big and dark when it's low, small and faint when high."""
    if not 0 <= d <= 1:
        return
    _, (sx, sy), scale = table.project(u, d, z)
    lift = min(z / 0.5, 1.0)
    sr = max(2, int(BALL_SIZE * scale * (1.1 - 0.6 * lift)))
    blend(frame, alpha * (0.55 - 0.35 * lift), (sx - sr, sy - sr, sx + sr + 1, sy + sr + 1),
          lambda img, ox, oy: cv2.ellipse(img, (int(sx) - ox, int(sy) - oy), (sr, max(1, sr // 3)),
                                          0, 0, 360, (0, 0, 0), -1, cv2.LINE_AA))


def draw_ball(frame, table, u, d, z, alpha=1.0):
    (bx, by), _, scale = table.project(u, d, z)
    r = max(3, int(BALL_SIZE * scale))

    def ball_shape(img, ox, oy):
        c = (int(bx) - ox, int(by) - oy)
        cv2.circle(img, c, r, BALL_COLOR, -1, cv2.LINE_AA)
        cv2.circle(img, c, r, (255, 255, 255), max(1, r // 12), cv2.LINE_AA)
        cv2.circle(img, (c[0] - r // 3, c[1] - r // 3), max(1, r // 4), (210, 235, 255), -1, cv2.LINE_AA)

    if alpha >= 1.0:
        ball_shape(frame, 0, 0)
    else:
        blend(frame, alpha, (bx - r - 2, by - r - 2, bx + r + 3, by + r + 3), ball_shape)


def draw_bounce_mark(frame, table, ball, age):
    """Small fading ring where the ball touched the table."""
    if age > 0.6:
        return
    d = ball["bounce_d"]
    x, y = table.screen(table.u_for_x(ball["x"] * table.w, d), d)
    r = int(BALL_SIZE * table.width_at(d) * (1 + age))
    blend(frame, 0.8 * (1 - age / 0.6), (x - r - 3, y - r - 3, x + r + 4, y + r + 4),
          lambda img, ox, oy: cv2.ellipse(img, (int(x) - ox, int(y) - oy), (r, max(1, r // 3)),
                                          0, 0, 360, (255, 255, 255), 2, cv2.LINE_AA))


def draw_paddle(frame, x, y, r, alpha, hand="right"):
    """Red paddle with head radius r pixels at (x, y), handle angled toward the paddle hand,
    and a white dot at the center - the point the hit check uses."""
    side = 1 if hand == "right" else -1
    handle_len, handle_w = 0.85 * r, 0.3 * r
    ang = math.radians(90 - 25 * side)            # pointing down, tilted toward your hand
    hx = x + math.cos(ang) * (r + handle_len / 2)
    hy = y + math.sin(ang) * (r + handle_len / 2)
    handle = cv2.boxPoints(((hx, hy), (handle_len, handle_w), math.degrees(ang))).astype(np.float32)

    def shape(img, ox, oy):
        cv2.fillConvexPoly(img, (handle - [ox, oy]).astype(np.int32), (60, 110, 160), cv2.LINE_AA)
        c = (int(x) - ox, int(y) - oy)
        cv2.circle(img, c, int(r), (30, 30, 200), -1, cv2.LINE_AA)
        cv2.circle(img, c, int(r), (20, 20, 120), max(2, int(r / 12)), cv2.LINE_AA)

    pad = handle_len + r + 4
    blend(frame, alpha, (x - r - pad, y - r - 4, x + r + pad, y + r + pad), shape)
    dot = max(4, int(r / 8))
    cv2.circle(frame, (int(x), int(y)), dot, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, (int(x), int(y)), dot, (0, 0, 0), 1, cv2.LINE_AA)
