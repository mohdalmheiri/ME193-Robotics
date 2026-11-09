/*
  safe_app sketch: the latch (moved only when the Python side asks), the
  LED matrix (showing whatever picture the Python side sends), and the
  MPU-6050 motion sensor on the box floor (tamper detection).

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
          MPU-6050: VCC -> 3.3V, GND -> GND, SCL -> SCL, SDA -> SDA.
*/
#include "Arduino_LED_Matrix.h"
#include "Arduino_RouterBridge.h"
#include <Wire.h>
#include <vector>

// ---- LED matrix: 13 columns x 8 rows ----
const int MATRIX_ROWS = 8;
const int MATRIX_COLS = 13;
Arduino_LED_Matrix matrix;
uint8_t frame[MATRIX_ROWS * MATRIX_COLS];

const int PIN_A = 9;    // Maker Drive M1A
const int PIN_B = 10;   // Maker Drive M1B

// ---- tuned moves (copied from latch_motor_test) ----
const int SPEED = 150;           // 0-255
const int LOCK_MS = 240;         // wall -> straight out (90 degrees). Was 215, tuned while the board ran
                                 // on the laptop's USB power. On the power bank (through the hub) the motor
                                 // is a little slower, and 215 ms only reached about 70-85 degrees.
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

// ---- MPU-6050 motion sensor (tamper detection) ----
// Read 100 times a second. Each reading becomes two "movement" numbers:
//   shake = how far the acceleration is from its recent average, in mg
//           (thousandths of gravity). Still: ~0. A knock: a sharp spike.
//           Lifting or tilting the box: a change that lasts.
//   turn  = how far the rotation speed is from its recent average, in
//           degrees per second (the average removes the sensor's own offset).
// The sketch keeps the BIGGEST value of each since Python last asked
// (Python asks about 10 times a second), so even a 10 ms knock is caught.
// While the latch motor moves, and for QUIET_AFTER_MOVE_MS after, the peaks
// are not recorded: the safe must not alarm at its own motor.
const uint8_t MPU_ADDR = 0x68;
const unsigned long SAMPLE_INTERVAL_MS = 10;     // 100 readings per second
const unsigned long QUIET_AFTER_MOVE_MS = 1000;  // ignore movement this long after a move
const float AVG_WEIGHT = 0.01;   // how fast the "recent average" follows: about 1 s to settle
TwoWire *mpuWire = &Wire;
bool mpuFound = false;
int mpuWhoAmI = -1;               // the sensor's ID register: 0x68 (104) for an MPU-6050
unsigned long lastSampleMillis = 0;
unsigned long quietUntil = 0;     // movement before this time is ignored (motor moving / just moved)
float avgA[3] = {0, 0, 1};        // recent average acceleration (g), starts at "flat, still"
float avgG[3] = {0, 0, 0};        // recent average rotation (deg/s): the sensor's own offset
bool haveAverage = false;
// Peaks since Python last asked. Written by loop(), read and cleared by
// motion() on the Bridge's thread. Single float writes are atomic on this
// chip, so the worst case of the two meeting is one 10 ms reading's peak
// being lost, never a garbled number.
volatile float peakShake = 0;     // mg
volatile float peakTurn = 0;      // deg/s
volatile float nowA[3] = {0, 0, 0};

bool probe(TwoWire &wire) {
  wire.begin();
  wire.beginTransmission(MPU_ADDR);
  return wire.endTransmission() == 0;   // 0 = the sensor answered
}

void writeReg(uint8_t reg, uint8_t val) {
  mpuWire->beginTransmission(MPU_ADDR);
  mpuWire->write(reg);
  mpuWire->write(val);
  mpuWire->endTransmission();
}

int16_t readWord(uint8_t reg) {
  mpuWire->beginTransmission(MPU_ADDR);
  mpuWire->write(reg);
  mpuWire->endTransmission(false);
  mpuWire->requestFrom((uint8_t)MPU_ADDR, (uint8_t)2);
  int16_t hi = mpuWire->read();
  int16_t lo = mpuWire->read();
  return (int16_t)((hi << 8) | lo);
}

void setupMpu() {
  writeReg(0x6B, 0x00);   // PWR_MGMT_1: wake up
  writeReg(0x1C, 0x10);   // ACCEL_CONFIG: +/-8 g (4096 per g): room for hard knocks, still fine detail
  writeReg(0x1B, 0x08);   // GYRO_CONFIG: +/-500 deg/s (65.5 per deg/s)
}

// Look for the sensor on both I2C buses (the header's SDA/SCL may be either).
// Called at start-up and then every PROBE_RETRY_MS until it answers, so a
// sensor that is slow to start, or a wire pushed back in, is picked up
// without restarting the app.
const unsigned long PROBE_RETRY_MS = 2000;
unsigned long lastProbeMillis = 0;

void findMpu() {
  lastProbeMillis = millis();
  bool onWire = probe(Wire);
  bool onWire1 = !onWire && probe(Wire1);
  if (!(onWire || onWire1)) return;
  mpuWire = onWire ? &Wire : &Wire1;
  setupMpu();
  mpuWire->beginTransmission(MPU_ADDR);     // read the ID register (0x75): 0x68 for an MPU-6050
  mpuWire->write(0x75);
  mpuWire->endTransmission(false);
  mpuWire->requestFrom((uint8_t)MPU_ADDR, (uint8_t)1);
  mpuWhoAmI = mpuWire->read();
  haveAverage = false;                      // start the averages fresh
  mpuFound = true;
}

void sampleMpu() {
  float a[3], g[3];
  a[0] = readWord(0x3B) / 4096.0;  a[1] = readWord(0x3D) / 4096.0;  a[2] = readWord(0x3F) / 4096.0;
  g[0] = readWord(0x43) / 65.5;    g[1] = readWord(0x45) / 65.5;    g[2] = readWord(0x47) / 65.5;
  if (a[0] == 0 && a[1] == 0 && a[2] == 0) {   // all zero: the sensor restarted asleep (loose wire)
    setupMpu();
    return;
  }
  if (!haveAverage) {                           // first reading: start the averages here
    for (int i = 0; i < 3; i++) { avgA[i] = a[i]; avgG[i] = g[i]; }
    haveAverage = true;
  }
  float da = 0, dg = 0;
  for (int i = 0; i < 3; i++) {
    da += (a[i] - avgA[i]) * (a[i] - avgA[i]);
    dg += (g[i] - avgG[i]) * (g[i] - avgG[i]);
    avgA[i] += AVG_WEIGHT * (a[i] - avgA[i]);   // the averages slowly follow the readings
    avgG[i] += AVG_WEIGHT * (g[i] - avgG[i]);
    nowA[i] = a[i];
  }
  float shake = sqrt(da) * 1000.0;             // g -> mg
  float turn = sqrt(dg);
  if (millis() < quietUntil) return;           // motor moving or just moved: don't count it
  if (shake > peakShake) peakShake = shake;
  if (turn > peakTurn) peakTurn = turn;
}

// Called by Python about 10 times a second. Returns
// [sensor found (1/0), its ID, peak shake mg, peak turn deg/s, ax, ay, az (g), quiet (1/0)]
// and starts the next peaks from zero.
std::vector<float> motion() {
  std::vector<float> out = {mpuFound ? 1.0f : 0.0f, (float)mpuWhoAmI, peakShake, peakTurn,
                            nowA[0], nowA[1], nowA[2], millis() < quietUntil ? 1.0f : 0.0f};
  peakShake = 0;
  peakTurn = 0;
  return out;
}

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
    quietUntil = millis() + 60000;   // stay quiet until loop() finishes the move and sets the real end
  }
  return state;
}

// Called by Python through the Bridge with one character per LED, row by
// row: '0' = off ... '7' = brightest. Python picks the picture
// (matrix_patterns.py); this only lights it.
void draw_frame(String levels) {
  int count = MATRIX_ROWS * MATRIX_COLS;
  for (int i = 0; i < count; i++) {
    char ch = (i < (int)levels.length()) ? levels.charAt(i) : '0';
    frame[i] = (ch >= '0' && ch <= '7') ? ch - '0' : 0;
  }
  matrix.draw(frame);
}

void setup() {
  matrix.begin();
  matrix.clear();
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  stopMotor();                    // nothing moves at power-up

  Bridge.begin();
  Bridge.provide("latch", latch);
  Bridge.provide("draw_frame", draw_frame);
  Bridge.provide("motion", motion);

  // Find the motion sensor. Give it half a second to power up first (the
  // step-recorder app needed the same wait); if it still doesn't answer,
  // loop() keeps trying every PROBE_RETRY_MS.
  delay(500);
  findMpu();
  quietUntil = millis() + 60000;  // quiet through the startup homing (set properly below)

  delay(STARTUP_WAIT_MS);         // hands clear
  unlockMove();                   // home: against the wall, a known spot
  delay(300);
  lockMove();                     // then shut
  pending = CMD_STATUS;           // forget anything asked for during startup
  quietUntil = millis() + QUIET_AFTER_MOVE_MS;
  state = STATE_LOCKED;
}

void loop() {
  int cmd = pending;
  if (cmd == CMD_STATUS) {
    // No move to do: read the motion sensor every 10 ms.
    unsigned long now = millis();
    if (!mpuFound && now - lastProbeMillis >= PROBE_RETRY_MS) {
      findMpu();                  // not found yet: try again every 2 s
    }
    if (mpuFound && now - lastSampleMillis >= SAMPLE_INTERVAL_MS) {
      lastSampleMillis = now;
      sampleMpu();
    } else {
      delay(1);
    }
    return;
  }
  pending = CMD_STATUS;
  // latch() only accepts a move that changes something (a second LOCK while
  // locked would push the arm past 90 degrees, as nothing stops it there).
  if (cmd == CMD_UNLOCK) {
    unlockMove();
    quietUntil = millis() + QUIET_AFTER_MOVE_MS;   // the box may still wobble for a moment
    state = STATE_UNLOCKED;
  } else if (cmd == CMD_LOCK) {
    lockMove();
    quietUntil = millis() + QUIET_AFTER_MOVE_MS;
    state = STATE_LOCKED;
  }
}
