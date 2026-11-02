# Arcade visual effects for game.py: particle bursts, floating text, screen shake,
# red edge flash. Drawing only - no game rules here.
import math
import random

import cv2
import numpy as np

GRAVITY = 900            # px/s^2 (at 720p) pulling particles down
MAX_PARTICLES = 150      # oldest particles are dropped beyond this (keeps big bursts cheap)
CONFETTI = [(0, 215, 255), (0, 255, 0), (255, 255, 0), (255, 0, 255), (0, 140, 255), (255, 255, 255)]


class Effects:
    def __init__(self):
        self.particles = []     # [x, y, vx, vy, born, life, color, size]
        self.floaters = []      # [text, x, y, born, life, color]
        self.shake = None       # (start, duration)
        self.red = None         # (start, duration)
        self._last = None       # time of the last draw(), for particle motion

    def burst(self, now, x, y, S, n=30, colors=((0, 255, 0), (180, 255, 180), (255, 255, 255)),
              speed=420, life=0.7, up=0.0):
        """Particles flying out from (x, y) pixels; up > 0 throws them upward (confetti)."""
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            v = random.uniform(0.3, 1.0) * speed * S
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v - up * S, now,
                                   life * random.uniform(0.6, 1.0), random.choice(colors),
                                   max(2, int(random.uniform(3, 7) * S))])
        self.particles = self.particles[-MAX_PARTICLES:]

    def floater(self, now, text, x, y, color, life=0.9):
        self.floaters.append([text, x, y, now, life, color])

    def start_shake(self, now, duration=0.35):
        self.shake = (now, duration)

    def start_red_flash(self, now, duration=0.45):
        self.red = (now, duration)

    def draw(self, frame, now, S, text_fn):
        """Move and draw particles and floating text (call every frame)."""
        dt = 0.0 if self._last is None else min(now - self._last, 0.1)
        self._last = now
        alive = []
        for p in self.particles:
            age = now - p[4]
            if age > p[5]:
                continue
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += GRAVITY * S * dt
            r = max(1, int(p[7] * (1 - age / p[5])))
            cv2.circle(frame, (int(p[0]), int(p[1])), r, p[6], -1, cv2.LINE_AA)
            alive.append(p)
        self.particles = alive

        alive = []
        for f in self.floaters:
            age = now - f[3]
            if age > f[4]:
                continue
            text_fn(frame, f[0], (int(f[1]), int(f[2] - 120 * S * age / f[4])), 1.6 * S, f[5], 4, center=True)
            alive.append(f)
        self.floaters = alive

    def post(self, frame, now, S):
        """Red edge flash and screen shake, applied to the finished frame. Returns the frame."""
        h, w = frame.shape[:2]
        if self.red and now - self.red[0] < self.red[1]:
            fade = 1 - (now - self.red[0]) / self.red[1]
            for k, (frac, alpha) in enumerate(((0.10, 0.25), (0.05, 0.35))):   # two bands = soft edge
                b = int(frac * min(w, h))
                for (x0, y0, x1, y1) in ((0, 0, w, b), (0, h - b, w, h), (0, b, b, h - b), (w - b, b, w, h - b)):
                    roi = frame[y0:y1, x0:x1]
                    red = np.empty_like(roi)
                    red[:] = (0, 0, 255)
                    cv2.addWeighted(red, alpha * fade, roi, 1 - alpha * fade, 0, roi)
        if self.shake and now - self.shake[0] < self.shake[1]:
            amp = 16 * S * (1 - (now - self.shake[0]) / self.shake[1])
            M = np.float32([[1, 0, random.uniform(-amp, amp)], [0, 1, random.uniform(-amp, amp)]])
            frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        return frame


def draw_speaker(frame, x, y, S, muted):
    """Small speaker icon with sound waves, or a red X when muted. (x, y) = top-left."""
    s = S
    body = np.int32([[x, y + 8 * s], [x + 8 * s, y + 8 * s], [x + 18 * s, y], [x + 18 * s, y + 30 * s],
                     [x + 8 * s, y + 22 * s], [x, y + 22 * s]])
    cv2.fillPoly(frame, [body], (0, 0, 0), cv2.LINE_AA)
    cv2.polylines(frame, [body], True, (255, 255, 255), max(1, int(2 * s)), cv2.LINE_AA)
    c = (int(x + 18 * s), int(y + 15 * s))
    if muted:
        a, b = (int(x + 24 * s), int(y + 6 * s)), (int(x + 40 * s), int(y + 24 * s))
        cv2.line(frame, a, b, (0, 0, 255), max(2, int(3 * s)), cv2.LINE_AA)
        cv2.line(frame, (a[0], b[1]), (b[0], a[1]), (0, 0, 255), max(2, int(3 * s)), cv2.LINE_AA)
    else:
        for r in (8, 15):
            cv2.ellipse(frame, c, (int(r * s), int(r * s)), 0, -45, 45, (255, 255, 255), max(1, int(2 * s)),
                        cv2.LINE_AA)
