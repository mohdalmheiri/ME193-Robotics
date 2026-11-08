/*
  latch_motor_test.ino
  --------------------
  Goal: swing the latch arm between its two positions through the Cytron
  Maker Drive, with timings that suit the arm mounted in the box.

  The two positions:
    UNLOCKED = arm folded back against the box wall (out of the way)
    LOCKED   = arm sticking straight out, 90 degrees from the wall (blocking)

  Why the wall matters: a TT motor has no sensor telling us where the arm
  is. We can only say "run for this many milliseconds". Small errors (a
  slightly weaker battery, a little friction) would add up each swing and
  the arm would slowly drift. So UNLOCK runs a bit LONGER than needed and
  lets the arm press gently against the wall. The wall stops it in exactly
  the same place every time, which resets any drift. The wall is the arm's
  "home". LOCK then always starts from that known spot.

  How the Maker Drive works (from the table on the back of the board):
    M1A on,  M1B off  -> motor spins one way
    M1A off, M1B on   -> motor spins the other way
    both the same     -> motor stops
  analogWrite (PWM) flicks the pin on and off very fast so the motor gets
  only part of the power: a lower number = slower, gentler motor.

  Wiring: Maker Drive M1A -> D9, M1B -> D10, GND -> UnoQ GND.
*/

const int PIN_A = 9;    // Maker Drive header pin M1A
const int PIN_B = 10;   // Maker Drive header pin M1B

// ---- the numbers you'll tune ----
const int SPEED = 150;        // 0-255. Same gentle speed as before.
const int LOCK_MS = 215;      // wall -> straight out. 200 and 210 ms were short of 90 degrees,
                              // 220 ms a bit over, so 215.

// UNLOCK (straight out -> wall) happens in two parts, so the arm reaches the
// wall slowly instead of slamming into it at full speed:
const int UNLOCK_FAST_MS = 90;   // part 1: full SPEED for under half the way back
                                 // (160 ms got the arm nearly to the wall, too fast;
                                 // 110 ms still tapped the wall a bit harder than wanted)
const int SOFT_SPEED = 75;       // part 2: a much slower speed for the rest. This is the
                                 // speed the arm hits the wall at, so it sets how hard the
                                 // tap is (90 still tapped a bit firmly)...
const int UNLOCK_SOFT_MS = 450;  // ...for this long. Long enough to reach the wall and
                                 // press on it gently (that is what stops drift). At speed 90,
                                 // 180 ms stopped short and the gap grew every cycle; 350 ms was
                                 // enough. Slower speed needs more time. Too long is safe here:
                                 // at this low speed the arm just leans on the wall.
// Tuning: still hits hard -> lower UNLOCK_FAST_MS or SOFT_SPEED.
//         stops before the wall -> raise UNLOCK_SOFT_MS.
//         buzzes but doesn't move in part 2 -> SOFT_SPEED is too weak; raise it.

// Which pin turns the arm TOWARD the wall? true = M1A, false = M1B.
// Confirmed by watching the direction check on 2026-11-07: M1A = toward
// the wall. If the motor wires are ever swapped, flip this to false.
const bool WALL_IS_M1A = true;

// Direction check: when true, the sketch waits 15 s, then does ONE lock
// (out) and ONE unlock (back), and nothing else. Start with the arm against
// the wall. If WALL_IS_M1A is right, the arm goes out and comes back. If it
// is wrong, the arm first stays still (pressing into the wall), then swings
// AWAY from it. Set to false for the normal lock/unlock loop.
const bool DIRECTION_CHECK = false;

void stopMotor() {
  // Both pins off = stop.
  analogWrite(PIN_A, 0);
  analogWrite(PIN_B, 0);
}

void drive(bool towardWall, int speed, int ms) {
  // Turn on the one pin that gives the wanted direction at this speed and
  // wait. Does NOT stop afterwards, so two drive() calls in a row run smoothly
  // one into the other; the caller stops the motor when done.
  bool useA = (towardWall == WALL_IS_M1A);   // toward the wall uses M1A only if WALL_IS_M1A
  analogWrite(PIN_A, useA ? speed : 0);
  analogWrite(PIN_B, useA ? 0 : speed);
  delay(ms);
}

void unlock() {
  // Back to the wall (home): fast most of the way, then slow for the last
  // stretch, so the arm reaches the wall gently and presses on it briefly.
  drive(true, SPEED, UNLOCK_FAST_MS);
  drive(true, SOFT_SPEED, UNLOCK_SOFT_MS);
  stopMotor();
}

void lock() {
  // From the wall out to straight out (90 degrees).
  drive(false, SPEED, LOCK_MS);
  stopMotor();
}

void setup() {
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  stopMotor();          // make sure nothing moves at startup

  if (DIRECTION_CHECK) {
    delay(15000);       // 15 seconds to get ready and start watching
    lock();             // should swing OUT from the wall
    delay(2000);
    unlock();           // should swing BACK to the wall
    return;             // loop() does nothing more in check mode
  }

  delay(5000);          // 5 seconds to get your hands clear
  // We don't know where the arm is at power-on, so the first move is always
  // "go home": UNLOCK pushes it to the wall.
  unlock();
}

void loop() {
  if (DIRECTION_CHECK) {
    return;             // check mode: nothing more after the single swing in setup()
  }
  delay(3000);          // pause so you can see where the arm stopped
  lock();
  delay(3000);
  unlock();
}
