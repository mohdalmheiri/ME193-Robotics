"""Live scrolling spectrogram from the microphone. Whistle at it!

Run:  my_env/bin/python spectogram.py
Close the window (or Ctrl+C) to stop.
"""
import queue

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
from matplotlib.animation import FuncAnimation

SAMPLE_RATE = 44100
FFT_SIZE = 2048          # ~21.5 Hz per bin
HOP = 1024               # new column every ~23 ms
HISTORY_SEC = 8          # seconds of history shown
MAX_FREQ = 5000          # whistles live roughly 500-4000 Hz

n_cols = int(HISTORY_SEC * SAMPLE_RATE / HOP)
freqs = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)
n_bins = np.searchsorted(freqs, MAX_FREQ)
window = np.hanning(FFT_SIZE)

spec = np.full((n_bins, n_cols), -100.0)
buffer = np.zeros(FFT_SIZE, dtype=np.float32)
audio_q = queue.Queue()


def audio_callback(indata, frames, time, status):
    audio_q.put(indata[:, 0].copy())


fig, ax = plt.subplots(figsize=(10, 5))
img = ax.imshow(spec, origin="lower", aspect="auto", cmap="magma",
                extent=[-HISTORY_SEC, 0, 0, MAX_FREQ], vmin=-80, vmax=0)
fig.colorbar(img, ax=ax, label="dB")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Frequency (Hz)")
title = ax.set_title("Whistle into the mic...")
peak_line = ax.axhline(0, color="cyan", lw=1, alpha=0.7)


def update(_):
    global spec, buffer
    peak_hz = None
    while not audio_q.empty():
        chunk = audio_q.get()
        buffer = np.concatenate([buffer[len(chunk):], chunk])
        mag = np.abs(np.fft.rfft(buffer * window))[:n_bins]
        db = 20 * np.log10(mag / (FFT_SIZE / 4) + 1e-10)
        spec = np.roll(spec, -1, axis=1)
        spec[:, -1] = db
        # Only report a peak if it clearly stands out (i.e. a whistle, not noise)
        low = np.searchsorted(freqs, 300)
        k = low + np.argmax(db[low:])
        if db[k] > -45 and db[k] - np.median(db) > 30:
            peak_hz = freqs[k]
    img.set_data(spec)
    if peak_hz is not None:
        title.set_text(f"Peak: {peak_hz:,.0f} Hz")
        peak_line.set_ydata([peak_hz, peak_hz])
    return img, title, peak_line


with sd.InputStream(channels=1, samplerate=SAMPLE_RATE, blocksize=HOP,
                    callback=audio_callback):
    anim = FuncAnimation(fig, update, interval=30, blit=False,
                         cache_frame_data=False)
    plt.show()
