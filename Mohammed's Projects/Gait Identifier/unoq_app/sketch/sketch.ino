#include "Arduino_RouterBridge.h"
#include <Wire.h>
#include <vector>

const uint8_t MPU_ADDR = 0x68;
TwoWire *mpuWire = &Wire;

const unsigned long SAMPLE_INTERVAL_MS = 10; // 100 Hz
unsigned long lastSampleMillis = 0;
uint32_t sampleCounter = 0;

// Samples are queued here as a flat list of floats:
// [counter, ax, ay, az, gx, gy, gz,  counter, ax, ay, az, gx, gy, gz,  ...]
// Python pulls (and clears) this with Bridge.call("get_batch") a few times a
// second, so individual Bridge.notify() calls are never made at 100 Hz.
std::vector<float> sampleBuffer;
const size_t FIELDS_PER_SAMPLE = 7;
const size_t MAX_BUFFERED_SAMPLES = 2000; // ~20s backlog cap if Python ever stalls

bool probe(TwoWire &wire) {
  wire.begin();
  wire.beginTransmission(MPU_ADDR);
  return wire.endTransmission() == 0;
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

// Exposed to Python: returns every sample collected since the last call, then empties the buffer.
std::vector<float> get_batch() {
  std::vector<float> out = sampleBuffer;
  sampleBuffer.clear();
  return out;
}

void setup() {
  Bridge.begin();
  Bridge.provide("get_batch", get_batch);
  delay(500);

  bool onWire = probe(Wire);
  delay(50);
  bool onWire1 = probe(Wire1);
  if (onWire) {
    mpuWire = &Wire;
  } else if (onWire1) {
    mpuWire = &Wire1;
  }

  writeReg(0x6B, 0x00); // PWR_MGMT_1: wake up
  writeReg(0x1C, 0x18); // ACCEL_CONFIG: AFS_SEL=3 -> +/-16g
  writeReg(0x1B, 0x18); // GYRO_CONFIG: FS_SEL=3 -> +/-2000 deg/s

  sampleBuffer.reserve(FIELDS_PER_SAMPLE * 50);
}

void loop() {
  unsigned long now = millis();
  if (now - lastSampleMillis < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMillis = now;

  int16_t ax = readWord(0x3B);
  int16_t ay = readWord(0x3D);
  int16_t az = readWord(0x3F);
  int16_t gx = readWord(0x43);
  int16_t gy = readWord(0x45);
  int16_t gz = readWord(0x47);

  // +/-16g -> 2048 LSB/g, +/-2000 deg/s -> 16.4 LSB/(deg/s)
  float axg = ax / 2048.0;
  float ayg = ay / 2048.0;
  float azg = az / 2048.0;
  float gxd = gx / 16.4;
  float gyd = gy / 16.4;
  float gzd = gz / 16.4;

  if (sampleBuffer.size() >= MAX_BUFFERED_SAMPLES * FIELDS_PER_SAMPLE) {
    // Python isn't keeping up: drop the oldest sample to bound memory use.
    // The counter gap this leaves behind is exactly what lets Python detect it.
    sampleBuffer.erase(sampleBuffer.begin(), sampleBuffer.begin() + FIELDS_PER_SAMPLE);
  }

  sampleBuffer.push_back((float)sampleCounter);
  sampleBuffer.push_back(axg);
  sampleBuffer.push_back(ayg);
  sampleBuffer.push_back(azg);
  sampleBuffer.push_back(gxd);
  sampleBuffer.push_back(gyd);
  sampleBuffer.push_back(gzd);
  sampleCounter++;
}
