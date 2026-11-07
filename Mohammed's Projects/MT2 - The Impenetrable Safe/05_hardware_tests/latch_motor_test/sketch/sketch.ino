/*
  latch_motor_test.ino
  --------------------
  Goal: check that the UnoQ can swing the latch arm both ways
  through the Cytron Maker Drive, and find the right timing.

  How the Maker Drive works (from the table on the back of the board):
    M1A on,  M1B off  -> motor spins FORWARD
    M1A off, M1B on   -> motor spins BACKWARD
    both the same     -> motor stops

  Instead of fully "on", we use analogWrite (PWM): the pin flicks on and
  off very fast, so the motor only gets part of the power. A lower
  number = slower, gentler motor. That's safer for a latch and pulls
  less power from the UnoQ.

  Wiring: Maker Drive M1A -> D9, M1B -> D10, GND -> UnoQ GND.
*/

const int PIN_A = 9;    // Maker Drive header pin M1A
const int PIN_B = 10;   // Maker Drive header pin M1B

// ---- the two numbers you'll tune ----
const int SPEED = 150;      // 0-255. Start gentle; raise it if the arm is too weak.
const int MOVE_MS = 300;    // how long the motor runs for one swing, in milliseconds.

void stopMotor() {
  // Both pins off = stop.
  analogWrite(PIN_A, 0);
  analogWrite(PIN_B, 0);
}

void unlock() {
  // Spin one way for MOVE_MS, then stop.
  analogWrite(PIN_A, SPEED);
  analogWrite(PIN_B, 0);
  delay(MOVE_MS);
  stopMotor();
}

void lock() {
  // Spin the other way for the same time, so the arm returns.
  analogWrite(PIN_A, 0);
  analogWrite(PIN_B, SPEED);
  delay(MOVE_MS);
  stopMotor();
}

void setup() {
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  stopMotor();          // make sure nothing moves at startup
  delay(2000);          // 2 seconds to get your hands clear
}

void loop() {
  unlock();
  delay(2000);          // pause so you can see where the arm stopped
  lock();
  delay(2000);
}
