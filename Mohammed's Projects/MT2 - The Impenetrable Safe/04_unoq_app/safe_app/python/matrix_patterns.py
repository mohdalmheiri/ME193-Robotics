"""
matrix_patterns.py - what the board's 13 x 8 LED matrix shows for each state.

Each pattern is drawn as text: one string per row, 13 characters wide.
  "#" = bright, "+" = dim, "." = off.
pattern_for() picks the picture; main.py sends it to the sketch, which
lights the LEDs (brightness 0-7).

  padlock (closed)   IDLE: asleep, locked
  three empty boxes  awake, no digits yet (the "ready" pattern)
  filled boxes       one box fills per digit entered (dots, not numbers)
  bottom row         a bar that fills while a digit, fist or palm is held
  check mark         for 2 s when the code is right ...
  open padlock       ... then for as long as it stays unlocked
  X                  for 2 s after a wrong code
  number             during the lockout: the seconds left, blinking "!" in
                     between
  "?"                the latch's state isn't known yet (board starting up)
  camera icon        the camera isn't working (unplugged or wrong picture size)
"""
from lock_logic import IDLE, LOCKOUT, UNLOCKED, READY, WAIT_ZERO

ROWS, COLS = 8, 13
SHOW_EVENT_S = 2.0        # how long the check mark / X stays up

PADLOCK = [
    ".....###.....",
    "....#...#....",
    "....#...#....",
    "...#######...",
    "...#######...",
    "...###.###...",
    "...#######...",
    ".............",
]
PADLOCK_OPEN = [
    "........###..",
    ".......#...#.",
    ".......#.....",
    "...#######...",
    "...#######...",
    "...###.###...",
    "...#######...",
    ".............",
]
CHECK = [
    ".............",
    "..........#..",
    ".........#...",
    "........#....",
    "..#....#.....",
    "...#..#......",
    "....##.......",
    ".............",
]
CROSS = [
    ".............",
    "...#.....#...",
    "....#...#....",
    ".....#.#.....",
    "......#......",
    ".....#.#.....",
    "....#...#....",
    "...#.....#...",
]
BANG = [
    "......#......",
    "......#......",
    "......#......",
    "......#......",
    "......#......",
    ".............",
    "......#......",
    ".............",
]
CAMERA = [   # a little camera: shown when the webcam isn't working
    ".............",
    "...##........",
    ".##########..",
    ".#...##...#..",
    ".#..#..#..#..",
    ".#...##...#..",
    ".##########..",
    ".............",
]
QUESTION = [
    ".....###.....",
    "....#...#....",
    "........#....",
    ".......#.....",
    "......#......",
    ".............",
    "......#......",
    ".............",
]
DIGITS = {  # 3 x 5 font for the lockout countdown
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", "###", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", "..#", "..#"],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
}


def blank():
    return [["."] * COLS for _ in range(ROWS)]


def boxes(filled, progress):
    """Three 3x3 boxes: empty (dim outline) or filled (bright) per digit, plus the hold bar."""
    g = blank()
    for i in range(3):
        x0 = i * 5                                    # boxes at columns 0-2, 5-7, 10-12
        for dy in range(3):
            for dx in range(3):
                edge = dy != 1 or dx != 1
                if i < filled:
                    g[2 + dy][x0 + dx] = "#"
                elif edge:
                    g[2 + dy][x0 + dx] = "+"
    bar(g, progress)
    return g


def bar(g, progress):
    """Bottom row fills left to right while something is being held (0..1)."""
    for x in range(round(progress * COLS)):
        g[ROWS - 1][x] = "#"


def number(n):
    """Up to 2 digits, centered (lockout countdown)."""
    g, s = blank(), str(max(0, min(99, n)))
    x = 6 - (len(s) * 4 - 1) // 2
    for ch in s:
        for r, row in enumerate(DIGITS[ch]):
            for c, v in enumerate(row):
                if v == "#":
                    g[1 + r][x + c] = "#"
        x += 4
    return g


def pattern_for(lock, now, board_state, camera_ok):
    """The picture for this moment, as a list of 8 rows of 13 characters."""
    if not camera_ok:
        return CAMERA
    event, when = lock.event
    recent = now - when < SHOW_EVENT_S
    if lock.state == LOCKOUT:
        left = int(lock.lockout_until - now) + 1
        return BANG if int(now * 2) % 4 == 0 else number(left)   # mostly the countdown, a "!" now and then
    if recent and event == "wrong":
        return CROSS
    if lock.state == UNLOCKED:
        if recent and event == "right":
            return CHECK
        g = [list(r) for r in PADLOCK_OPEN]
        bar(g, lock.hold_progress(now))              # palm held to lock again
        return g
    if lock.state in (READY, WAIT_ZERO):
        return boxes(len(lock.digits), lock.hold_progress(now))
    if board_state not in ("locked", "unlocked"):
        return QUESTION                               # IDLE but the latch's state isn't known yet
    g = [list(r) for r in PADLOCK]                    # IDLE
    bar(g, lock.hold_progress(now))                   # palm held to wake up
    return g


def to_bits(pattern):
    """Rows of characters -> the sketch's string of brightness digits, one per LED (row by row)."""
    level = {"#": "7", "+": "2", ".": "0"}
    return "".join(level[ch] for row in pattern for ch in row)
