# Sumo Wrestling (HW5)

A human-driven LEGO sumo robot with shared control. You drive with the LEGO Controller; the robot
**refuses** to drive forward over the blue tape edge and **boosts** to full power when the opponent is
close and you're already charging. A behavior tree on the laptop fuses three inputs: the controller
levers, a LEGO Color Sensor watching for the tape, and an HC-SR04 ultrasonic sensor on an Arduino UNO Q
that publishes the opponent's distance over MQTT.

```
LEGO Controller ─┐
Color Sensor ────┼─ Bluetooth ─► laptop: behavior_tree.py ─► Double Motor (tank drive + sad song)
                 │                    ▲
HC-SR04 ─► UNO Q ─── MQTT (ME193/Mohammed/sumo/distance)
```

## Files

| File | What it does |
|---|---|
| `sumo.py` | Main program: connects everything, runs the behavior tree 20×/s |
| `behavior_tree.py` | The policy (pure logic, no hardware) |
| `test_behavior_tree.py` | Tests the policy without hardware |
| `sad_song.py` | The losing tune on the Double Motor's beeper |
| `connect_test.py` | Hardware check: prints color sensor, IMU, levers and button |
| `watch_distance.py` | Prints the UNO Q's distance readings from MQTT |
| `unoq_app/` | UNO Q app: `sketch/sketch.ino` reads the HC-SR04, `python/main.py` publishes it |

## The behavior tree

Checked top to bottom 20 times a second; the first branch that applies wins.

| # | Branch | Condition | Action | Light |
|---|---|---|---|---|
| 1 | OUT | Enter pressed in the `sumo.py` terminal (or the controller button) | Stop, play sad song, stay stopped (press again to reset) | Red |
| 2 | NO_EDGE | Color sensor not reporting | Stop | Orange |
| 3 | EDGE_PUSH | At the edge, but opponent ≤ 30 cm (reading ≤ 0.3 s old) and both levers forward | Full power forward: push them out instead of refusing | Purple |
| 4 | EDGE | Blue tape seen (and 0.3 s after), nothing close in front | Forward blocked, backward allowed | Yellow |
| 5 | BOOST | Opponent ≤ 30 cm, reading ≤ 0.3 s old, both levers forward | Full power forward | Magenta |
| 6 | DRIVE | Otherwise | Wheels follow the levers | Green |

EDGE_PUSH is the one branch that fuses all three inputs (levers + color sensor + HC-SR04):
at the edge, driving forward normally means falling out, but with the opponent right in front
it means pushing them out.

**The "out" signal is the Enter key.** The controller's button doesn't report to the laptop,
so `sumo.py` watches its terminal for Enter instead (the button still works if it ever does).
Press Enter when you're out (stop + sad song), and Enter again to reset for the next round.

## Running on a new laptop

```bash
git clone https://github.com/mohdalmheiri/ME193-Robotics.git
cd ME193-Robotics
python3 -m venv .venv
source .venv/bin/activate
pip install -r "Mohammed's Projects/Sumo Wrestling/requirements.txt"
cd "Mohammed's Projects/Sumo Wrestling"
python test_behavior_tree.py     # should say "All tests passed!"
python sumo.py
```

Before `python sumo.py`:

- **Bluetooth on.** The LEGO parts (Double Motor, Color Sensor, Controller) connect over Bluetooth
  through the **orange connection card, serial 0994** (`CARD_COLOR` / `CARD_SERIAL` in `sumo.py`).
- **One laptop at a time.** The LEGO parts can only be connected to one laptop, so close
  `sumo.py` (or `connect_test.py`) on the other laptop first.
- **UNO Q running.** The "Sumo Distance" app (`unoq_app/`) must be running on the UNO Q, and the
  board must be on Wi-Fi so it can reach `test.mosquitto.org`. Without it, the robot still drives,
  but BOOST and EDGE_PUSH never trigger. Check it with `python watch_distance.py`.
- **"Out" = Enter.** Press Enter in the `sumo.py` terminal when you're out, and Enter again to
  reset for the next round.
- **Sad trombone.** The laptop sound uses macOS `afplay`. On Windows/Linux only the robot beeps.

## Setup

**Laptop:** `pip install -r requirements.txt` (pins `legoeducation==1.2.0` and `paho-mqtt==2.1.0`)

**UNO Q:** `unoq_app/` is a complete app (`app.yaml`, `python/`, `sketch/` with `sketch.yaml`).
Either copy it into your ArduinoApps deploy kit and run `python3 tools/deploy.py <app-folder>`, or
in App Lab create an app named "Sumo Distance" and replace its files with these. Connect the board to
Wi-Fi, and click Run.

**HC-SR04 wiring:**

| HC-SR04 | UNO Q |
|---|---|
| VCC | 5V |
| GND | GND |
| Trig | D2 |
| Echo | 1 kΩ resistor → D3, and D3 → 2 kΩ resistor → GND (voltage divider, 5 V → 3.3 V) |

## Test order

1. `python test_behavior_tree.py`: policy tests (no hardware)
2. `python connect_test.py`: read the color numbers over floor vs. tape, check levers and button
3. `python sad_song.py`: hear the song
4. Run the UNO Q app, then `python watch_distance.py`: wave your hand in front of the HC-SR04
5. Robot on blocks (wheels off the table): `python sumo.py`, check each branch's light
6. In a taped ring: practice matches

## Tuning

| Setting | File | What it does |
|---|---|---|
| `TAPE_MODE`, `TAPE_COLORS`, `TAPE_HUE_RANGE`, `TAPE_MIN_SATURATION` | `sumo.py` | How the blue tape is recognized |
| `LEFT_SIGN`, `RIGHT_SIGN`, `SWAP_LEVERS` | `sumo.py` | Fix wheels that spin the wrong way |
| `LEVER_SIGN` | `sumo.py` | Set to -1 if pushing the levers forward reads negative |
| `CARD_COLOR`, `CARD_SERIAL` | `sumo.py` | Connection card the LEGO parts pair with (orange, `"0994"`; keep the serial a string so the leading zero stays) |
| `BOOST_DISTANCE_CM` | `behavior_tree.py` | How close the opponent must be to boost |
| `CHARGE_THRESHOLD` | `behavior_tree.py` | How far forward the levers must be to count as charging |
| `STALE_AFTER_S` | `behavior_tree.py` | When an MQTT distance reading is too old to trust |
| `TAPE_HOLD_S` | `behavior_tree.py` | How long forward stays blocked after leaving the tape |

### Measured tape settings

Read with `connect_test.py` on our ring:

| Surface | Hue | Saturation |
|---|---|---|
| Floor | ~15-21 | ~30-38 |
| Blue tape | ~206 | ~62-77 |

Based on these, `sumo.py` uses `TAPE_MODE = "hue"` with
`TAPE_HUE_RANGE = (180, 240)` and `TAPE_MIN_SATURATION = 55`. The tape is well inside the hue range
and above the saturation cutoff, while the floor fails both checks.
