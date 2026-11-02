"""Ping-pong scoreboard for the UNO Q LED matrix (8 x 13).

Subscribes to the live score that game.py publishes and shows it:
  ME193/Rogers/Mohammed/game   "0-0" | "7-5" | "11-7 WIN" | "9-11 LOSS" | "7-0 WIN (SKUNK)"
  ME193/Rogers/Mohammed        the overall record, e.g. "23.0"
Both topics are retained, so the board shows the latest state even if it starts after
the game. paho reconnects by itself if the Wi-Fi drops, and on_connect subscribes again.

Same structure as the HW4 MQTT LED Matrix app: Python builds each frame and sends it
to the sketch with Bridge.notify("draw_frame", bits).
"""
import random
import threading
import time

import paho.mqtt.client as mqtt

from arduino.app_utils import App, Bridge

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
GAME_TOPIC = "ME193/Rogers/Mohammed/game"
RECORD_TOPIC = "ME193/Rogers/Mohammed"

MATRIX_ROWS = 8
MATRIX_COLS = 13
SCROLL_DELAY_SECONDS = 0.08
IDLE_SECONDS = 20          # no game message for this long -> scroll the record

# 3x5 pixel font (from the HW4 app); unsupported characters become a space.
FONT = {
    "0": ["###", "#.#", "#.#", "#.#", "###"],
    "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"],
    "3": ["###", "..#", "###", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"],
    "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"],
    "7": ["###", "..#", "..#", "..#", "..#"],
    "8": ["###", "#.#", "###", "#.#", "###"],
    "9": ["###", "#.#", "###", "..#", "###"],
    "C": [".##", "#..", "#..", "#..", ".##"],
    "E": ["###", "#..", "##.", "#..", "###"],
    "G": [".##", "#..", "#.#", "#.#", ".##"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "N": ["#.#", "##.", "#.#", ".##", "#.#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."],
    "U": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#.#", "#.#", "#.#", "###", "#.#"],
    "!": [".#.", ".#.", ".#.", "...", ".#."],
    "-": ["...", "...", "###", "...", "..."],
    " ": ["...", "...", "...", "...", "..."],
}
CHAR_ROWS, CHAR_COLS, CHAR_GAP = 5, 3, 1
ROW_OFFSET = (MATRIX_ROWS - CHAR_ROWS) // 2

# 8 x 13 pictures ('#' = on)
SMILEY = ["....#####....",
          "...#.....#...",
          "..#.#...#.#..",
          "..#.......#..",
          "..#.#...#.#..",
          "..#..###..#..",
          "...#.....#...",
          "....#####...."]
SAD = ["....#####....",
       "...#.....#...",
       "..#.#...#.#..",
       "..#.......#..",
       "..#..###..#..",
       "..#.#...#.#..",
       "...#.....#...",
       "....#####...."]
BLANK = ["." * MATRIX_COLS] * MATRIX_ROWS
FULL = ["#" * MATRIX_COLS] * MATRIX_ROWS


# ---------------------------------------------------------------------------
# Frames: a frame is a row-major '0'/'1' string of MATRIX_ROWS * MATRIX_COLS pixels
# ---------------------------------------------------------------------------
def picture(rows):
    return "".join("1" if ch == "#" else "0" for row in rows for ch in row)


def render_text(text):
    """List of columns (left to right), each MATRIX_ROWS pixels (0/1) tall."""
    columns = []
    for ch in text.upper():
        glyph = FONT.get(ch, FONT[" "])
        for c in range(CHAR_COLS):
            col = [0] * MATRIX_ROWS
            for r in range(CHAR_ROWS):
                if glyph[r][c] == "#":
                    col[ROW_OFFSET + r] = 1
            columns.append(col)
        columns.extend([[0] * MATRIX_ROWS for _ in range(CHAR_GAP)])
    return columns[:-CHAR_GAP] if columns else columns


def frame_from_columns(window):
    bits = [0] * (MATRIX_ROWS * MATRIX_COLS)
    for c, col in enumerate(window):
        for r, v in enumerate(col):
            bits[r * MATRIX_COLS + c] = v
    return "".join(str(b) for b in bits)


def text_frames(text, hold=0.4):
    """Frames showing `text`: centered and still if it fits, otherwise scrolling once across."""
    cols = render_text(text)
    blank = [0] * MATRIX_ROWS
    if len(cols) <= MATRIX_COLS:
        left = (MATRIX_COLS - len(cols)) // 2
        window = [blank] * left + cols + [blank] * (MATRIX_COLS - len(cols) - left)
        return [(frame_from_columns(window), hold)]
    strip = [blank] * MATRIX_COLS + cols + [blank] * MATRIX_COLS
    return [(frame_from_columns(strip[i:i + MATRIX_COLS]), SCROLL_DELAY_SECONDS)
            for i in range(len(strip) - MATRIX_COLS + 1)]


def sparkle(n=6, density=0.25):
    return [("".join("1" if random.random() < density else "0" for _ in range(MATRIX_ROWS * MATRIX_COLS)), 0.1)
            for _ in range(n)]


def go_animation():
    """New match: a box that grows from the middle, then GO flashing."""
    frames = []
    for k in range(1, 7):
        rows = []
        for r in range(MATRIX_ROWS):
            row = ""
            for c in range(MATRIX_COLS):
                edge = max(abs(r - 3.5) - 0.5, abs(c - 6) * 8 / 13)
                row += "#" if k - 1 <= edge < k else "."
            rows.append(row)
        frames.append((picture(rows), 0.07))
    go = text_frames("GO", hold=0.3)
    return frames + (go + [(picture(BLANK), 0.15)]) * 3


def win_animation():
    """Win: sparkles, then a blinking smiley."""
    return sparkle() + [(picture(SMILEY), 0.35), (picture(BLANK), 0.15)] * 3 + [(picture(SMILEY), 0.8)]


def loss_animation():
    return [(picture(SAD), 1.8)]


def skunk_animation():
    """Skunk: a white stripe sweeping across (like a skunk's back), then three full flashes."""
    frames = []
    for shift in range(-4, MATRIX_COLS + 4):
        rows = ["".join("#" if abs(c - shift - (r - 3.5) * 0.5) < 1.5 else "." for c in range(MATRIX_COLS))
                for r in range(MATRIX_ROWS)]
        frames.append((picture(rows), 0.05))
    return frames + [(picture(FULL), 0.12), (picture(BLANK), 0.12)] * 3


# ---------------------------------------------------------------------------
# What to show for each game message
# ---------------------------------------------------------------------------
def plan_for(message):
    """(intro frames played once, frames repeated afterwards) for a game-topic message."""
    msg = message.strip().upper()
    score = msg.split()[0] if msg else ""
    if "(SKUNK)" in msg:
        return skunk_animation() + text_frames("SKUNK"), text_frames(score) + [(picture(BLANK), 0.3)]
    if "WIN" in msg:
        return win_animation(), text_frames(f"WIN {score}") + [(picture(BLANK), 0.3)]
    if "LOSS" in msg:
        return loss_animation(), text_frames(score) + [(picture(BLANK), 0.3)]
    if score == "0-0":
        return go_animation(), text_frames(score, hold=1.0)
    return [], text_frames(score, hold=1.0)


class Display:
    def __init__(self):
        self.intro, self.repeat, self.i = [], text_frames("WAIT") + [(picture(BLANK), 0.3)], 0

    def show(self, intro, repeat):
        self.intro, self.repeat, self.i = list(intro), repeat, 0

    def next_frame(self):
        if self.intro:
            return self.intro.pop(0)
        frame = self.repeat[self.i % len(self.repeat)]
        self.i += 1
        return frame


# ---------------------------------------------------------------------------
# MQTT (background thread) -> latest messages for the display loop
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_inbox = {"game": None, "record": None}


def on_connect(client, userdata, flags, rc, properties=None):
    # also runs after every reconnect, so the subscriptions come back (and the
    # retained messages are delivered again)
    if rc != 0:
        print(f"MQTT connection refused by {MQTT_BROKER} ({rc}) - retrying")
        return
    print(f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}, subscribing")
    client.subscribe(GAME_TOPIC)
    client.subscribe(RECORD_TOPIC)


def on_disconnect(client, userdata, *args):
    print("MQTT disconnected - paho will keep trying to reconnect")


def on_message(client, userdata, msg):
    text = msg.payload.decode("utf-8", errors="replace").strip()
    print(f"MQTT {msg.topic}: {text!r}")
    with _lock:
        if msg.topic == GAME_TOPIC and text:
            _inbox["game"] = text
        elif msg.topic == RECORD_TOPIC and text:
            _inbox["record"] = text


CLIENT_ID = f"unoq-scoreboard-{random.randrange(16 ** 6):06x}"   # unique id on the public broker
try:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)   # paho-mqtt 2.x
except AttributeError:
    mqtt_client = mqtt.Client(client_id=CLIENT_ID)                                     # paho-mqtt 1.x
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
mqtt_client.loop_start()

display = Display()
state = {"record": None, "last_game": 0.0, "idle": False}


def loop():
    now = time.time()
    with _lock:
        game, record = _inbox["game"], _inbox["record"]
        _inbox["game"] = _inbox["record"] = None

    if record is not None:
        try:
            state["record"] = int(float(record))
        except ValueError:
            pass
    if game is not None:
        display.show(*plan_for(game))
        state["last_game"], state["idle"] = now, False
    elif not display.intro and now - state["last_game"] > IDLE_SECONDS and (not state["idle"] or record is not None):
        state["idle"] = True   # nothing new for a while (or a new record while idle): scroll the record
        rec = "-" if state["record"] is None else str(state["record"])
        display.show([], text_frames(f"REC {rec}") + [(picture(BLANK), 0.5)])

    bits, seconds = display.next_frame()
    Bridge.notify("draw_frame", bits)
    time.sleep(seconds)


App.run(user_loop=loop)
