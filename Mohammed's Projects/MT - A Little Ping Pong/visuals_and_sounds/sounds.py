# Game sounds, synthesized with numpy (no sound files) and played through one
# sounddevice (PortAudio) output stream. A tiny mixer in the audio callback adds up
# all sounds that are playing, so they overlap and play() never blocks the video.
# (Not pygame: its bundled SDL2 clashes with the SDL2 inside OpenCV on macOS.)
import threading

import numpy as np
import sounddevice as sd

RATE = 44100
VOLUME = 0.5


def _t(seconds):
    return np.arange(int(RATE * seconds)) / RATE


def _env(n, attack=0.005, decay=None):
    """Quick fade-in, then exponential fade-out (or a hold + short fade-out if decay is None)."""
    a = np.minimum(1.0, np.arange(n) / max(1, int(RATE * attack)))
    if decay is None:
        tail = int(RATE * 0.02)
        r = np.ones(n)
        r[-tail:] = np.linspace(1, 0, tail)
        return a * r
    return a * np.exp(-np.arange(n) / (RATE * decay))


def _tone(freq, seconds, decay=None, shape="sine"):
    t = _t(seconds)
    phase = 2 * np.pi * freq * t
    if shape == "square":
        wave = np.sign(np.sin(phase)) * 0.6 + 0.4 * np.sin(2 * phase)
    else:
        wave = np.sin(phase)
    return wave * _env(len(t), decay=decay)


def make_sounds():
    rng = np.random.default_rng(0)
    tock_t = _t(0.06)
    tock = (0.8 * np.sin(2 * np.pi * 950 * tock_t) + 0.5 * rng.uniform(-1, 1, len(tock_t))
            * np.exp(-tock_t / 0.004)) * np.exp(-tock_t / 0.015)                 # wooden "tock"
    pop_t = _t(0.12)
    pop = np.sin(2 * np.pi * (1300 * pop_t + 3000 * pop_t ** 2)) * np.exp(-pop_t / 0.04)   # rising "pop"
    buzz = _tone(110, 0.4, shape="square") * 0.7                              # low buzz
    jingle = np.concatenate([_tone(f, 0.11, decay=0.08) for f in (523, 659, 784)] + [_tone(1047, 0.25, decay=0.12)])
    bot_t = _t(0.07)
    bot_hit = (0.8 * np.sin(2 * np.pi * 620 * bot_t) + 0.4 * rng.uniform(-1, 1, len(bot_t))
               * np.exp(-bot_t / 0.004)) * np.exp(-bot_t / 0.02)              # lower, rounder "tock"
    smash_t = _t(0.25)
    smash = (np.sin(2 * np.pi * (900 * smash_t + 4000 * smash_t ** 2)) * 0.8
             + 0.6 * rng.uniform(-1, 1, len(smash_t)) * np.exp(-smash_t / 0.03)) * np.exp(-smash_t / 0.08)
    chime = np.concatenate([_tone(880, 0.09, decay=0.07), _tone(1319, 0.22, decay=0.12)])   # point won
    lost = np.concatenate([_tone(392, 0.12, decay=0.1), _tone(294, 0.25, decay=0.15)]) * 0.8  # point lost
    win = np.concatenate([_tone(f, 0.12, decay=0.1) for f in (523, 659, 784, 1047, 784)]
                         + [_tone(1047, 0.5, decay=0.25)])
    lose = np.concatenate([_tone(f, 0.18, decay=0.15) for f in (523, 466, 415)] + [_tone(349, 0.6, decay=0.3)])
    return {
        "bot_hit": bot_hit,
        "smash": smash,
        "point_won": chime,
        "point_lost": lost,
        "win": win,
        "lose": lose,
        "bounce": tock,
        "hit": pop,
        "miss": buzz,
        "count": _tone(660, 0.13),
        "go": _tone(1320, 0.3, decay=0.15),
        "record": jingle,
    }


class Sounds:
    """play(name) returns immediately. Never crashes the game: no audio device = silent."""

    MAX_VOICES = 8

    def __init__(self):
        self.muted = False
        self.ok = False
        self._active = []            # [samples, position] of sounds still playing
        self._lock = threading.Lock()
        try:
            self._sounds = {name: np.clip(wave * VOLUME, -1, 1).astype(np.float32)
                            for name, wave in make_sounds().items()}
            self._stream = sd.OutputStream(samplerate=RATE, channels=1, dtype="float32",
                                           blocksize=256, latency="low", callback=self._mix)
            self._stream.start()
            self.ok = True
        except Exception as exc:
            print(f"Sound disabled ({exc})")

    def _mix(self, outdata, frames, time_info, status):
        out = np.zeros(frames, np.float32)
        with self._lock:
            for voice in self._active:
                chunk = voice[0][voice[1]:voice[1] + frames]
                out[:len(chunk)] += chunk
                voice[1] += frames
            self._active = [v for v in self._active if v[1] < len(v[0])]
        outdata[:, 0] = np.clip(out, -1, 1)

    def play(self, name):
        if self.ok and not self.muted:
            with self._lock:
                self._active = self._active[-(self.MAX_VOICES - 1):] + [[self._sounds[name], 0]]

    def toggle_mute(self):
        self.muted = not self.muted
        print("Sound muted" if self.muted else "Sound on")

    def close(self):
        if self.ok:
            self._stream.stop()
            self._stream.close()
