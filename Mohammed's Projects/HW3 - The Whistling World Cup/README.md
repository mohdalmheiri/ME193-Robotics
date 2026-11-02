# The Whistling World Cup (HW3)

A LEGO car controlled by sound. The laptop mic listens for notes played on
a recorder (the instrument) and for claps: each calibrated recorder note is a
driving command and a clap means stop. On match day two cars play ball vs.
goalie, and they coordinate the start and the result over MQTT.

## How it works

`whistling.py` grabs a live microphone stream with `pyaudio`, listens for
one of 6 calibrated recorder notes, and maps each one to a command via a
simple per-note lookup table:

| Sound | Command |
|---|---|
| recorder notes 1-3 (any of the 3 lowest) | REVERSE, one fixed (slow) speed |
| recorder note 4 | FORWARD, one fixed (faster) speed |
| recorder note 5 | LEFT -- a bounded 90° turn, then stops |
| recorder note 6 (highest) | RIGHT -- a bounded 90° turn, then stops |
| one clap | STOP |
| 3 quick RIGHT turns in a row (**ball role only**) | GOAL -- publishes to MQTT, ends the match |

Notes 1-3 originally each drove a different FORWARD speed tier, but
weren't reliably distinguishable from each other in practice, so they
were collapsed into one outcome — any of the 3 lowest notes means the
same thing. FORWARD and REVERSE were then swapped (so the group of 3
notes is REVERSE and the single note 4 is FORWARD) and their speeds set
further apart: FORWARD faster, REVERSE slower, since reversing blind is
riskier. STOP dropped from two claps to one. The 6 notes still aren't
hardcoded to specific frequencies — they're calibrated to *your* recorder
at startup (play each one, lowest to highest, when prompted), since the
exact pitch depends on the instrument and fingering, and calibration
itself didn't change through any of this. The whole note-to-command
mapping lives in one list, `NOTE_COMMANDS`, near the top of
`whistling.py` — reordering or reassigning any note is a one-line change
there. On match day the car is also assigned a role — **ball** or
**goalie** — and the two cars coordinate the match over MQTT.

### Match logic (MQTT)

- `ME193/Rogers` — instructor-published `"start"` trigger. Both roles
  subscribe and hold at STOP until it arrives.
- `RESULT_TOPIC` (`ME193/Rogers/whistling-world-cup` by default) — used
  for the two outcome messages, each published as `"<event>:<role>"`:
  - `"caught:ball"` — the ball's own light sensor saw the goalie get close
    (`CATCH_REFLECTION`, held for `CATCH_HOLD_FRAMES` readings). The ball
    stops, publishes this, and plays its death song immediately (it
    doesn't wait for its own message to echo back). The goalie, on
    receiving it, plays the success song.
  - `"goal:ball"` — the ball gave the special scoring command: 3 quick
    RIGHT turns in a row (`GOAL_TAP_COUNT` within `GOAL_TAP_WINDOW_S`),
    reusing the same RIGHT-turn signal notes already use, just counted.
    The ball stops, publishes this, and plays its success song. The
    goalie, on receiving it, plays the death song.

  Each side reacts to the *other* role's message (a client ignores a
  message carrying its own role, since the broker echoes every publish
  back to its own subscribers too) — so both songs always come out
  opposite, as required. Both outcomes are role-gated at the source: only
  `state.role == "ball"` can trigger either `handle_caught()` (via its own
  sensor) or the goal-tap counter — the goalie's identical hardware/sound
  vocabulary never self-triggers either one. Its win comes entirely from
  *receiving* the ball's `"caught:ball"` message, not from anything it
  actively signals about itself.

  **You need to agree on `RESULT_TOPIC` (and this payload format) with
  whoever you're paired against before your match** — this is explicitly
  called out in the assignment ("you and your opponent need to agree on
  the messages sent"). The current value is just this team's placeholder;
  it has to match on both sides, and ideally be specific enough not to
  collide with another pair of teams also testing on the shared public
  broker at the same time.

### Calibration only runs once

Both the noise floor and your 6 recorder notes are saved to
`.calibration.json` (next to `whistling.py`, git-ignored) the first time
they're measured, and loaded from disk on every run after that — no more
redoing that setup every single time you start the script. Pass
`--recalibrate` if you change rooms/mics/instruments and want to redo it
for real.

### Design history (why a recorder, why claps for stop)

This control scheme went through several iterations, each teaching
something about what's actually reliable with real hardware and a real
(imprecise) human:

1. **Continuous whistle pitch → 4 zones.** Abandoned — whistling a wide,
   precise pitch range by mouth on demand turned out to be genuinely
   hard to hit reliably.
2. **Counting whistle taps.** Abandoned — timing several short whistle
   taps into one tight phrase was also fragile; real gaps between
   whistles didn't line up with a fixed timing window.
3. **Whistle duration + snap/clap by sound.** The snap half didn't work —
   this mic couldn't reliably pick up snaps above the noise floor at all.
4. **Humming for speed + whistle duration + clap counting.** Clap
   *counting* worked well (claps are crisp and repeatable, unlike
   whistle taps), which is why it's kept in every version since. Telling
   hum from whistle by pitch range, on top of everything else, got
   complicated to keep untangled.
5. **Speech recognition for left/right.** Considered, but a full ASR
   engine (cloud-dependent, or a large local model) for a two-word
   vocabulary was overkill and added real match-day risk.
6. **Phone tone generator + 4 zones + claps.** Playing a tone from a
   phone app sidesteps "can a human hold a precise pitch," which is what
   doomed version 1 — but coordinating a phone app added its own
   friction on match day.
7. **Current version: a recorder (the instrument) + claps.** A recorder
   gives the same precise-pitch benefit as the phone tone generator, but
   it's an instrument already in hand rather than a second device to
   manage — and unlike a slide-based tone, it naturally produces 6
   *discrete* notes, which maps more directly onto discrete speed levels
   than a continuous frequency zone did. Notes are calibrated per-
   instrument rather than hardcoded, the same way the noise floor already
   was, extended to cover pitch this time too. Claps stay for STOP
   because clap counting was the one piece that already proved reliable
   back in version 4.

## Hardware

- LEGO Education Double Motor (the car) and Color Sensor (the ball's catch
  sensor), both paired with one Connection Card
- A recorder (the instrument)
- A laptop mic (or AirPods, see below) and the laptop's own speakers for the
  success/death songs
- For a real match: a second laptop and car for the other team

### Using AirPods (or any Bluetooth mic) as the microphone

`whistling.py`'s device picker lists every input device pyaudio can see
and, when you press Enter, defaults to whichever one has `"airpods"` in
its name (`PREFERRED_MIC_NAME_CONTAINS` at the top of the file) rather
than the OS's own default input, which often stays pinned to the built-in
mic even once a headset is connected. Verified on this machine: once the
AirPods are connected over Bluetooth they show up as a dedicated input
device (`Tasha's AirPods #2`, mono, 24 kHz native — but 44.1 kHz also
opens fine) separate from their stereo output device.

One tradeoff worth knowing: using a Bluetooth headset's mic switches
macOS to the lower-quality HFP audio profile for that device, which would
also degrade anything played back through the *same* AirPods for as long
as the mic is in use. That's why `songs.py` doesn't just use the system
default output (which follows the AirPods once connected) -- it looks for
a device with `"macbook"` in its name (`PREFERRED_OUTPUT_NAME_CONTAINS`)
and plays the success/death songs there instead, so mic input (AirPods)
and song output (MacBook speakers) are deliberately split. Verified on
this machine: input is `Tasha's AirPods #2`, output resolves to `MacBook
Air Speakers`.

## Files

| File | What it does |
|---|---|
| [`whistling.py`](./whistling.py) | Main script: audio capture, note/clap policy, live display, LEGO driving, MQTT game logic |
| [`songs.py`](./songs.py) | Synthesizes and plays the success/death jingles through the computer speakers |
| [`lelib.py`](./lelib.py) | Shared LEGO Education wrapper (copied from the class library) |
| [`mqttlib.py`](./mqttlib.py) | Shared `paho-mqtt` wrapper (copied from the class library) |
| [`tools/send_mqtt.py`](./tools/send_mqtt.py) | Publishes one MQTT message (`"start"` on `ME193/Rogers` by default) to test the real match flow |
| [`tools/mqtt_chat.py`](./tools/mqtt_chat.py) | Two-way MQTT chat for checking that two laptops can reach the broker and each other |
| [`tools/wait_and_launch.py`](./tools/wait_and_launch.py) | Waits for `"start"`, asks for a role, then launches `whistling.py` |
| [`tools/spectogram.py`](./tools/spectogram.py) | Standalone live scrolling spectrogram (uses `sounddevice`) for checking note pitches |
| [`TESTING_CHECKLIST.md`](./TESTING_CHECKLIST.md) | Step-by-step checklist for the first run on real LEGO hardware |

## Setup and run

```
pip install --upgrade pip
pip install pyaudio numpy matplotlib paho-mqtt legoeducation
```

`tools/spectogram.py` also needs `sounddevice` (`pip install sounddevice`).

`pyaudio` needs the PortAudio C library installed first (`brew install
portaudio` on macOS) — see [Getting pyaudio installed without
Homebrew](#getting-pyaudio-installed-without-homebrew).

Before running on real hardware, fill in the `TODO`s at the top of
`whistling.py`:

- `CARD_SERIAL` / `CARD_COLOR` — your team's LEGO connection card (one
  physical card, used for both the Double Motor and the Color Sensor).
- `RESULT_TOPIC` — agree on a unique MQTT subtopic with the opposing team
  (e.g. `ME193/Rogers/<your-team-name>`) so your game-outcome messages
  don't collide with anyone else on the shared public broker.

Then, on match day:

```
python whistling.py --role ball      # on the ball's laptop
python whistling.py --role goalie    # on the goalie's laptop
```

The first run walks you through calibration (ambient noise, then your 6
recorder notes lowest to highest — 5s to hold each note, with a 1s pause
between so you can switch fingering); later runs reuse it automatically
(see [Calibration only runs once](#calibration-only-runs-once)). Both cars
then wait for a `"start"` message on `ME193/Rogers` before driving.

### Practicing before match day

You don't need the instructor's `"start"` message (or even a network
connection) to practice. `--practice` skips MQTT entirely and starts
driving live as soon as calibration finishes:

```
python whistling.py --role ball --practice
```

Everything else runs for real — the live plot, the actual note/clap
policy, and the Color Sensor's catch detection (getting "caught" in
practice mode still stops the car and plays the death song, it just has
no match to report the outcome to).

### Practicing without the LEGO hardware

`--no-lego` skips connecting to the Double Motor and Color Sensor.
Everything else still runs for real (mic, calibration, live plot, note
and clap detection), and each motor command is printed in the terminal
instead of being sent to the car:

```
python whistling.py --role ball --practice --no-lego
```

The light sensor always reads 0 in this mode, so the ball can't get
"caught". Scoring a goal (3 quick RIGHT turns) still works. Drop
`--practice` to also test the real MQTT flow, e.g. with `tools/send_mqtt.py`
sending `"start"`.

### Getting `pyaudio` installed without Homebrew

This machine had no Homebrew and no PortAudio headers, so `pip install
pyaudio` normally fails with `fatal error: 'portaudio.h' file not found`.
It's working now — PortAudio was built from source into a local prefix and
`pyaudio` was linked against that:

```
curl -sLo /tmp/portaudio.tgz http://files.portaudio.com/archives/pa_stable_v190700_20210406.tgz
tar xzf /tmp/portaudio.tgz -C /tmp
cd /tmp/portaudio
./configure --prefix="$HOME/AIRobotics/.portaudio" --disable-shared --enable-static
sed -i '' 's/-Werror//' Makefile   # newer clang trips on old unused-variable warnings treated as errors
make -j4 && make install
cp include/pa_mac_core.h "$HOME/AIRobotics/.portaudio/include/"  # not installed by `make install`, but pyaudio needs it

CFLAGS="-I$HOME/AIRobotics/.portaudio/include" \
LDFLAGS="-L$HOME/AIRobotics/.portaudio/lib -framework CoreAudio -framework AudioToolbox -framework AudioUnit -framework CoreFoundation -framework CoreServices" \
pip install pyaudio
```

If you do have Homebrew, it's much simpler: `brew install portaudio && pip
install pyaudio`.

## Tuning and notes

- **Note-onset transients are an untested edge case.** The very start of
  a note (breath attack before the tone stabilizes) is briefly
  broadband, in principle close to what a clap looks like.
  `PERCUSSIVE_MAX_S` (0.25s) should keep a full note from ever being read
  as percussive, but a real attack landing in its own frame right at the
  start of a note hasn't been tested on hardware -- watch for a phantom
  STOP right as a note starts, and tighten `PERCUSSIVE_MAX_S` or raise
  `PERCUSSIVE_RMS_MARGIN` if it happens. This is a bit more sensitive now
  that STOP only needs one clap instead of two.
- **The GOAL signal (3 quick RIGHT turns) can, in principle, be triggered
  by accident** if you happen to turn right 3 times within
  `GOAL_TAP_WINDOW_S` (8s) while just maneuvering normally, not intending
  to score. This was the pattern asked for, but it's worth knowing before
  match day -- if it turns out to be too easy to trigger accidentally,
  the fix is either a smaller `GOAL_TAP_WINDOW_S` or a pattern that
  doesn't double as a normal driving action.
- The FFT signal-analysis math (including the Welch-averaging fix and the
  quadratic-interpolation pitch refinement in `whistling.py`), `NoteDetector`'s
  nearest-match + debounce logic (including the fix that lets the *same*
  note re-fire after a confirmed silence gap, verified with a direct
  test — this also made the goal-tap counter possible, since 3 RIGHT
  commits in a row need the 2nd and 3rd to actually fire), `ClapStopDetector`'s
  state machine, the goal-tap counter and its ball-only role gate, the
  same role gate on catch-detection (verified: a simulated close-proximity
  reading fires a loss for `role="ball"` but does nothing for
  `role="goalie"`), `on_result_message`'s symmetric win/lose reaction
  (verified for both `"caught"` and `"goal"` events), calibration
  persistence (verified a 2nd run makes zero audio reads when a saved
  value exists), the AirPods-preferring device picker, and raw `pyaudio`
  mic capture were all verified directly with synthetic signals and real
  short mic captures. What's still untested is the full hardware loop —
  LEGO BLE connect/drive, an MQTT round-trip between two actual laptops,
  and actually playing a real recorder at a real microphone — which needs
  the LEGO hub, the recorder, and a second laptop in hand.
- `CATCH_REFLECTION` (the "opponent is right on top of the sensor"
  threshold), `FORWARD_SPEED`, and `REVERSE_SPEED` (currently deliberately
  slow) are starting guesses — recalibrate/retune them against your
  actual color sensor and how fast you actually want the car moving.
- **Fixed:** the live plot used to sit frozen during both calibration
  steps (only the printed terminal numbers updated) because calibration
  read raw audio directly instead of going through `classify_frame()`
  (the function that also updates the shared state the plot reads from).
  Both calibration steps now route through it, so the waveform/spectrum
  move during calibration too, not just once normal driving starts.
- If you want an independent sanity check of what your recorder's notes
  actually measure at, a standalone scrolling spectrogram (`tools/spectogram.py`,
  using `sounddevice` instead of `pyaudio`) is a handy second opinion —
  play your 6 notes at it and watch where the bright band lands on the
  frequency axis to confirm they're inside `NOTE_LOW_HZ`-`NOTE_HIGH_HZ`.

## Credits

- This code comes from
  [nsudofsky/ME193-Robotics](https://github.com/nsudofsky/ME193-Robotics/tree/main/The%20Whistling%20World%20Cup),
  plus a `--no-lego` practice mode added here.
