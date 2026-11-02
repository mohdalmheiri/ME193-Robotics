"""The losing tune: a "sad trombone" (wah, wah, wah, waaaah).

Plays in two places at once, so it's loud enough to hear in a noisy room:
  1. The laptop speakers (a generated brass-like sound, played with macOS `afplay`)
  2. The Double Motor's beeper, at higher pitches (small beepers sound loudest up high)

The LEGO beeper has no volume setting, so the laptop does the heavy lifting.
Turn the laptop volume up before a match.
"""
import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import wave

import legoeducation as le

# Descending "sad trombone": G, F#, F, then a long wobbly E.  (note Hz, seconds)
LAPTOP_NOTES = [(392.0, 0.45), (370.0, 0.45), (349.2, 0.45), (329.6, 1.6)]
SAMPLE_RATE = 22050
WAV_PATH = os.path.join(tempfile.gettempdir(), "sumo_sad_trombone.wav")

# Same melody two octaves up for the LEGO beeper: (Hz, beep repeats, pause after)
BEEPER_NOTES = [(1568, 2, 0.15), (1480, 2, 0.15), (1397, 2, 0.15), (1319, 6, 0.0)]


def _make_wav(path=WAV_PATH):
    """Build a brassy, loud trombone sound with only the standard library."""
    frames = bytearray()
    for i, (freq, dur) in enumerate(LAPTOP_NOTES):
        last = i == len(LAPTOP_NOTES) - 1
        n = int(SAMPLE_RATE * dur)
        phase = 0.0
        for k in range(n):
            t = k / SAMPLE_RATE
            f = freq
            if last:  # the "waaaah": vibrato that slowly droops
                f = freq * (1 + 0.025 * math.sin(2 * math.pi * 6 * t)) * (1 - 0.04 * t / dur)
            phase += 2 * math.pi * f / SAMPLE_RATE
            # brass-like tone: fundamental + strong overtones
            s = (math.sin(phase) + 0.6 * math.sin(2 * phase)
                 + 0.4 * math.sin(3 * phase) + 0.25 * math.sin(4 * phase))
            # short attack, and fade at the end of each note
            env = min(1.0, t / 0.03) * min(1.0, (dur - t) / (0.25 if last else 0.06))
            frames += struct.pack("<h", int(32767 * 0.9 * env * s / 2.25))
        frames += b"\x00\x00" * int(SAMPLE_RATE * 0.05)  # tiny gap between notes
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))
    return path


def _play_on_laptop():
    player = shutil.which("afplay")  # built into macOS
    if not player:
        print("(No afplay found; sad song plays on the robot only.)")
        return
    try:
        if not os.path.exists(WAV_PATH):
            _make_wav()
        subprocess.Popen([player, WAV_PATH])
    except Exception as e:
        print("Laptop sound failed:", e)


def _play_on_beeper(device):
    for freq, count, pause in BEEPER_NOTES:
        try:
            device.beep(pattern=le.SOUND_PATTERN_BEEP_SINGLE, frequency=freq, count=count)
        except Exception as e:
            print("Beep failed:", e)
            return
        time.sleep(pause)


def play_sad_song(device):
    """Called by sumo.py when we're out. Plays on the laptop and the robot together."""
    _play_on_laptop()
    if device is not None:
        _play_on_beeper(device)


if __name__ == "__main__":
    # Quick test:  python sad_song.py           (laptop + robot)
    #              python sad_song.py laptop    (laptop only, no LEGO needed)
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "laptop":
        _make_wav()
        _play_on_laptop()
        time.sleep(3.5)
    else:
        dm = le.DoubleMotor()
        dm.connect(card_color=le.LEGO_COLOR_ORANGE, card_serial="0994")
        if dm.connected:
            play_sad_song(dm)
            time.sleep(1)
            dm.disconnect()
        else:
            print("Couldn't connect to the Double Motor; playing on the laptop only.")
            _make_wav()
            _play_on_laptop()
            time.sleep(3.5)
