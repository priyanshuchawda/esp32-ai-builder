#include <Arduino.h>

const int LED_PIN = 2;

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); // Turn off the LED

  Serial.println();
  Serial.println("ESP32 Blink test stopped. LED is OFF.");
}

void loop() {
  // Do nothing
  delay(1000);
}
