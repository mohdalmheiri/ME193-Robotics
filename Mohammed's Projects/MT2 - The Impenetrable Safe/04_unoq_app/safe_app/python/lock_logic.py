"""
lock_logic.py - the safe's rules, in ONE place.

Used by both the board app (main.py) and the laptop version
(04_unoq_app/laptop_lock.py), so the two can never follow different rules.
It has no camera, screen or motor code: it is fed one network guess per
camera frame and calls latch.unlock() / latch.lock() when it decides to.
Time is passed in (never read from the clock here), so tests can feed
made-up guesses and times.

THE RULES, in plain words
-------------------------
The network guesses many times a second, and single guesses are shaky (a
hand moving into place can look like any number for a moment). So nothing
counts unless the same answer stays, at least SURE confident, for a while.

  IDLE       Asleep. Wake it with the "button": hold an OPEN PALM (5) for
             about WAKE_HOLD_S seconds. (On the laptop, SPACE also works.)
             The palm is judged more forgivingly than code digits (see
             "The palm" below), because waking up can't open anything.
  WAIT_ZERO  Show "0" (a fist, or no hand) for HOLD_ZERO_S. This pause comes
             after waking and after each digit, so holding a digit up
             doesn't type it again and again, and repeated digits like
             1-1-2 still work: 1, fist, 1, fist, 2.
  READY      Hold a digit 1-5 for HOLD_DIGIT_S to enter it.
  (3 digits) Right code -> UNLOCKED, the latch opens.
             Wrong code -> a strike; the digits are cleared, then a fist,
             then try again. MAX_STRIKES wrong codes in a row -> LOCKOUT.
  UNLOCKED   Open. Hold an open palm for WAKE_HOLD_S to lock it again.
             (On the laptop, L also works.)
  LOCKOUT    LOCKOUT_S seconds where everything is ignored, so trying all
             125 codes would take over 20 minutes.
  Timeout    Nothing accepted for IDLE_TIMEOUT_S while entering a code ->
             back to IDLE.

The palm (to wake up, and to lock again while open): it counts when MOST
of the guesses in the last WAKE_HOLD_S seconds say "5" at least WAKE_SURE
sure (WAKE_SHARE = 80%: about 8 of every 10), instead of EVERY guess in a
row. One shaky guess in the middle no longer starts the wait over. It also
uses a lower confidence bar (70%) than the digits (85%). That is safe
because the palm can only wake the lock up or lock it, never open it.

The palm only counts after the hand has shown "0" since the last change of
state ("armed"). Without that, a code ending in 5 would lock again at once,
as the hand keeps holding the 5 after the latch opens.
"""
from collections import deque

# ---- Settings (change these freely) ------------------------------------------
SURE = 0.85               # a guess counts only if the network is at least this sure (0-1)
WAKE_HOLD_S = 1.2         # the open palm ("button") is judged over this many seconds...
WAKE_SHARE = 0.8          # ...and counts when at least this share of those guesses say "5"...
WAKE_SURE = 0.70          # ...each at least this sure (lower than SURE: the palm can't open anything)
HOLD_DIGIT_S = 1.0        # a digit must be held (same sure answer on every frame) this many seconds
HOLD_ZERO_S = 0.5         # the fist / empty box between steps must be held this many seconds
MAX_STRIKES = 3           # wrong codes in a row before the lockout
LOCKOUT_S = 30.0          # how long the lockout lasts, in seconds
IDLE_TIMEOUT_S = 15.0     # no progress for this long while entering a code -> back to IDLE
PALM = 5                  # the "button" gesture: an open hand

# The states, as plain names (shown on screens as-is)
IDLE, READY, WAIT_ZERO, UNLOCKED, LOCKOUT = "IDLE", "READY", "WAIT_ZERO", "UNLOCKED", "LOCKOUT"


def read_code(path):
    """The secret code from safe_code.txt (kept out of Git): 3 digits 1-5, e.g. "3 1 4"."""
    if not path.exists():
        raise SystemExit(f"No {path.name}. Create it with the 3-digit code, e.g.: echo 3 1 4 > {path}")
    digits = [int(ch) for ch in path.read_text() if ch.isdigit()]
    if len(digits) != 3 or not all(1 <= d <= 5 for d in digits):
        raise SystemExit(f"{path.name} must hold 3 digits from 1 to 5 (found {digits}).")
    return digits


class LockLogic:
    """The rules above, as a small state machine (see the module notes)."""

    def __init__(self, code, latch):
        if len(code) != 3 or not all(1 <= d <= 5 for d in code):
            raise ValueError(f"the code must be 3 digits from 1 to 5, got {code}")
        self.code = list(code)
        self.latch = latch        # anything with unlock() and lock() returning True when the board agreed
        self.state = IDLE
        self.digits = []          # digits accepted so far in this attempt
        self.strikes = 0          # wrong codes in a row
        self.streak = None        # (answer, start time) of the current run of identical sure guesses
        self.armed = False        # has the hand shown "0" since the last change? (palm only counts then)
        self.palm_window = deque()  # (time, is_palm) for the guesses of the last WAKE_HOLD_S seconds
        self.watch_since = None   # when this state started feeding the palm window
        self.last_progress = 0.0  # when something was last accepted (for the timeout)
        self.lockout_until = 0.0
        self.event = (None, -1e9) # (name, time) of the last big moment: "right", "wrong", "lockout"
        self.message = "Hold an open palm to start"   # one line of feedback for screens

    # -- keys (laptop only) --
    def press_button(self, now):
        """SPACE on the laptop: wake up, or start the code over."""
        if self.state in (IDLE, READY, WAIT_ZERO):
            self._go(READY, now, "Show the first digit")
            self.digits = []

    def press_lock(self, now):
        """L on the laptop: lock again (only while open)."""
        if self.state == UNLOCKED:
            self._lock_again(now)

    # -- the board's real state --
    def follow_board(self, board_state):
        """Match the lock to what the board reports, if they disagree while nobody is typing.

        A board found open while IDLE -> UNLOCKED (so it can be locked again);
        a board that restarted (it homes and locks) while UNLOCKED -> IDLE.
        """
        if board_state == "unlocked" and self.state == IDLE:
            self._go(UNLOCKED, 0.0, "The latch is open. Hold an open palm to lock")
        elif board_state == "locked" and self.state == UNLOCKED:
            self._go(IDLE, 0.0, "The board says the latch is locked")

    # -- one camera frame --
    def update(self, answer, confidence, now):
        """Feed one network guess (answer 0..5, confidence 0..1) taken at time `now` (seconds)."""
        if self.state == LOCKOUT:
            if now >= self.lockout_until:
                self.strikes = 0
                self._go(IDLE, now, "Lockout over. Hold an open palm to start")
            return
        if self.state in (IDLE, UNLOCKED):
            self._palm(answer, confidence, now)       # the palm has its own, more forgiving rule
            return
        if self.state in (READY, WAIT_ZERO) and now - self.last_progress > IDLE_TIMEOUT_S:
            self.digits = []
            self._go(IDLE, now, f"No progress for {IDLE_TIMEOUT_S:.0f} s. Hold an open palm to start")
            return

        # Track how long the SAME sure answer has lasted. An unsure frame or a
        # different answer breaks the run, and the hold starts again from zero.
        if confidence < SURE:
            self.streak = None
            return
        if self.streak is None or self.streak[0] != answer:
            self.streak = (answer, now)
        held = now - self.streak[1]
        if answer == 0:
            self.armed = True     # a fist / empty box: the palm may count again

        if self.state == READY and answer != 0 and held >= HOLD_DIGIT_S:
            self._accept_digit(answer, now)
        elif self.state == WAIT_ZERO and answer == 0 and held >= HOLD_ZERO_S:
            self._go(READY, now, f"Show digit {len(self.digits) + 1}")

    def _palm(self, answer, confidence, now):
        """IDLE or UNLOCKED: wake up / lock again when the palm is MOSTLY there for WAKE_HOLD_S."""
        if answer == 0 and confidence >= SURE:
            self.armed = True                         # a fist / empty box: the palm may count now
        if self.watch_since is None:
            self.watch_since = now
        is_palm = self.armed and answer == PALM and confidence >= WAKE_SURE
        self.palm_window.append((now, is_palm))
        while self.palm_window[0][0] < now - WAKE_HOLD_S:   # forget guesses older than the window
            self.palm_window.popleft()
        watched_long_enough = now - self.watch_since >= WAKE_HOLD_S
        if watched_long_enough and self._palm_share() >= WAKE_SHARE:
            if self.state == IDLE:
                self.digits = []
                self._go(WAIT_ZERO, now, "Awake! Make a fist (0)")
            else:
                self._lock_again(now)

    def _palm_share(self):
        """Share of the guesses in the window that are a sure-enough palm (0..1)."""
        if not self.palm_window:
            return 0.0
        return sum(p for _, p in self.palm_window) / len(self.palm_window)

    def hold_progress(self, now):
        """How far the current hold is toward counting (0..1), for progress bars."""
        if self.state in (IDLE, UNLOCKED):
            return min(1.0, self._palm_share() / WAKE_SHARE) if self.armed else 0.0
        if self.streak is None:
            return 0.0
        answer, start = self.streak
        need = {READY: HOLD_DIGIT_S if answer != 0 else None,
                WAIT_ZERO: HOLD_ZERO_S if answer == 0 else None}.get(self.state)
        return min(1.0, (now - start) / need) if need else 0.0

    # -- inside steps --
    def _go(self, state, now, message):
        """Change state: the hold and the palm's "armed" flag start over."""
        self.state = state
        self.streak = None
        self.armed = False
        self.palm_window.clear()
        self.watch_since = None
        self.last_progress = now
        self.message = message

    def _lock_again(self, now):
        if self.latch.lock():
            self._go(IDLE, now, "Locked. Hold an open palm to start")
        else:                                         # the board didn't confirm: don't pretend it's shut
            self.palm_window.clear()                  # start the palm over before trying again
            self.watch_since = None
            self.message = "The board didn't answer: still open"

    def _accept_digit(self, digit, now):
        self.digits.append(digit)
        if len(self.digits) < len(self.code):
            self._go(WAIT_ZERO, now, "Got it. Make a fist (0)")
            return
        if self.digits == self.code:                  # the third digit: check the whole code
            self.strikes = 0
            self.digits = []
            if self.latch.unlock():
                self.event = ("right", now)
                self._go(UNLOCKED, now, "Correct! Hold an open palm to lock again")
            else:                                     # right code, but the latch didn't move
                self._go(IDLE, now, "Right code, but the latch didn't answer")
            return
        self.strikes += 1
        self.digits = []
        if self.strikes >= MAX_STRIKES:
            self.event = ("lockout", now)
            self._go(LOCKOUT, now, f"{MAX_STRIKES} wrong codes: locked out")
            self.lockout_until = now + LOCKOUT_S
        else:
            # The hand still shows the last digit, so a fist comes first;
            # otherwise that digit would be read again as the next try's first digit.
            self.event = ("wrong", now)
            self._go(WAIT_ZERO, now, f"Wrong code (strike {self.strikes} of {MAX_STRIKES}). Make a fist")
