/*
  safe_app sketch: the latch, moved only when the Python side asks.

  Every UNO Q app has two halves. The Python side (python/main.py) receives
  the laptop's UNLOCK / LOCK requests; this sketch, on the microcontroller,
  is the only part that can switch the motor pins. The two talk through the
  "Bridge": Python calls latch(1) or latch(2), and this sketch answers.

  The moves are the ones tuned in 05_hardware_tests/latch_motor_test
  (2026-11-07). If you retune them there, copy the numbers here too.

  At power-up the arm could be anywhere (the motor has no sensor), so the
  sketch "homes" it: UNLOCK presses it gently against the wall (a known
  spot), then LOCK swings it out. The safe always starts LOCKED. Honest
  catch: during those first seconds the latch is open for about half a
  second.

  Wiring: Maker Drive M1A -> D9, M1B -> D10, GND -> UNO Q GND.
*/
#include "Arduino_RouterBridge.h"

const int PIN_A = 9;    // Maker Drive M1A
const int PIN_B = 10;   // Maker Drive M1B

// ---- tuned moves (copied from latch_motor_test) ----
const int SPEED = 150;           // 0-255
const int LOCK_MS = 215;         // wall -> straight out (90 degrees)
const int UNLOCK_FAST_MS = 90;   // back toward the wall, fast part
const int SOFT_SPEED = 75;       // ...then slow, so it taps the wall gently
const int UNLOCK_SOFT_MS = 450;  // long enough to reach and lean on the wall
const bool WALL_IS_M1A = true;   // M1A turns the arm toward the wall (checked 2026-11-07)
const int STARTUP_WAIT_MS = 3000;  // time to get hands clear before the homing move

// What the sketch reports back (Python turns these into words)
const int STATE_LOCKED = 0;
const int STATE_UNLOCKED = 1;
const int STATE_BUSY = 2;        // starting up or in the middle of a move

// Requests from Python
const int CMD_STATUS = 0;
const int CMD_UNLOCK = 1;
const int CMD_LOCK = 2;

// "volatile": these are written by the Bridge (which runs alongside loop())
// and read by loop(), so the compiler must always read the real value.
volatile int pending = CMD_STATUS;   // a move waiting to be done (STATUS = none)
volatile int state = STATE_BUSY;     // busy until the startup homing is done

void stopMotor() {
  analogWrite(PIN_A, 0);
  analogWrite(PIN_B, 0);
}

void drive(bool towardWall, int speed, int ms) {
  // Power the one pin for the wanted direction, then wait. Doesn't stop
  // afterwards, so two drive() calls run smoothly into each other.
  bool useA = (towardWall == WALL_IS_M1A);
  analogWrite(PIN_A, useA ? speed : 0);
  analogWrite(PIN_B, useA ? 0 : speed);
  delay(ms);
}

void unlockMove() {
  drive(true, SPEED, UNLOCK_FAST_MS);       // fast most of the way back
  drive(true, SOFT_SPEED, UNLOCK_SOFT_MS);  // slow for the last bit, leaning on the wall
  stopMotor();
}

void lockMove() {
  drive(false, SPEED, LOCK_MS);             // out to 90 degrees
  stopMotor();
}

// Called by Python through the Bridge. It does NOT move the motor itself:
// it only writes down the request and answers straight away, and loop()
// does the move. That keeps the answer quick and means a move is never
// started from two places at once.
// A move that changes something is reported as BUSY at once, so the laptop
// never reads the old "locked" in the moment before loop() starts the move.
// A repeat (UNLOCK while unlocked, LOCK while locked) is simply ignored, and
// so is anything asked during the startup homing (state is BUSY then).
int latch(int cmd) {
  if ((cmd == CMD_UNLOCK && state == STATE_LOCKED) ||
      (cmd == CMD_LOCK && state == STATE_UNLOCKED)) {
    pending = cmd;
    state = STATE_BUSY;
  }
  return state;
}

void setup() {
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  stopMotor();                    // nothing moves at power-up

  Bridge.begin();
  Bridge.provide("latch", latch);

  delay(STARTUP_WAIT_MS);         // hands clear
  unlockMove();                   // home: against the wall, a known spot
  delay(300);
  lockMove();                     // then shut
  pending = CMD_STATUS;           // forget anything asked for during startup
  state = STATE_LOCKED;
}

void loop() {
  int cmd = pending;
  if (cmd == CMD_STATUS) {
    delay(10);                    // nothing to do; check again shortly
    return;
  }
  pending = CMD_STATUS;
  // latch() only accepts a move that changes something (a second LOCK while
  // locked would push the arm past 90 degrees, as nothing stops it there).
  if (cmd == CMD_UNLOCK) {
    unlockMove();
    state = STATE_UNLOCKED;
  } else if (cmd == CMD_LOCK) {
    lockMove();
    state = STATE_LOCKED;
  }
}
