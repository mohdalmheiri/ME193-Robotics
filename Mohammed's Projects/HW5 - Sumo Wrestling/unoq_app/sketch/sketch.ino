// UNO Q - microcontroller side. Reads the HC-SR04 ultrasonic sensor.
// Python calls read_distance() over the Bridge and gets back centimeters (-1 = no echo).
//
// Wiring:
//   HC-SR04 VCC  -> UNO Q 5V
//   HC-SR04 GND  -> UNO Q GND
//   HC-SR04 Trig -> D2
//   HC-SR04 Echo -> 1k resistor -> D3, and D3 -> 2k resistor -> GND
//                   (voltage divider: the Echo pin outputs 5 V, the UNO Q pins are 3.3 V)

#include <Arduino_RouterBridge.h>

const int TRIG_PIN = 2;
const int ECHO_PIN = 3;
const unsigned long TIMEOUT_US = 25000UL;   // ~4 m max; no echo after this = -1

float read_distance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);          // 10 us pulse starts a measurement
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long us = pulseIn(ECHO_PIN, HIGH, TIMEOUT_US);
  if (us == 0) return -1.0;
  return us / 58.0;                       // sound travels ~1 cm per 29 us, there and back
}

void setup() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  Bridge.begin();
  Bridge.provide("read_distance", read_distance);
}

void loop() {
}
