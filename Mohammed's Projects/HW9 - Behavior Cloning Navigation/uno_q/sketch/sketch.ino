// Nolop Navigator: the microcontroller side of HW9.
//
// Build step 1 of uno_q/README.md: nothing to do yet except open the Bridge, the link
// between this sketch and the Python program on the board's Linux side. Flashing this
// empty sketch also means the microcontroller isn't left running another app's sketch.
// Step 3 replaces it with HW7's sketch, which reads the ankle MPU-6050 100 times a second
// and hands the samples to Python in batches.

#include "Arduino_RouterBridge.h"

void setup() {
  Bridge.begin();
}

void loop() {
  delay(100);
}
