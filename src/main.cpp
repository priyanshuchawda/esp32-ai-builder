#include <Arduino.h>
#include <math.h>

namespace {
constexpr uint32_t kBaudRate = 115200;
constexpr uint32_t kSampleIntervalMs = 100;
constexpr int kStatusLedPin = 2;

float randomFloat(float minValue, float maxValue) {
  const float unit = static_cast<float>(esp_random()) /
                     static_cast<float>(UINT32_MAX);
  return minValue + unit * (maxValue - minValue);
}

int clampCsi(float value) {
  if (value < 1.0f) {
    return 1;
  }
  return static_cast<int>(roundf(value));
}
}  // namespace

void setup() {
  Serial.begin(kBaudRate);
  pinMode(kStatusLedPin, OUTPUT);
}

void loop() {
  static float timeSeconds = 0.0f;
  static bool ledState = false;

  const int64_t timestampMs = static_cast<int64_t>(millis());
  const float baseline = 20.0f + 5.0f * sinf(2.0f * PI * 0.05f * timeSeconds);
  const float noise = randomFloat(-1.5f, 1.5f);
  const bool hasSpike = (esp_random() % 100U) < 5U;
  const float spike = hasSpike ? ((esp_random() % 2U) == 0U ? 30.0f : -25.0f) : 0.0f;
  const float signal = baseline + noise + spike;
  const int rssi = -50 + static_cast<int>(0.2f * signal) +
                   static_cast<int>(esp_random() % 3U) - 1;

  int csi[6];
  for (int i = 0; i < 6; ++i) {
    csi[i] = clampCsi(signal + randomFloat(-2.0f, 2.0f));
  }

  Serial.printf("%lld,%d,%d,%d,%d,%d,%d,%d\n",
                timestampMs,
                rssi,
                csi[0],
                csi[1],
                csi[2],
                csi[3],
                csi[4],
                csi[5]);

  ledState = !ledState;
  digitalWrite(kStatusLedPin, ledState ? HIGH : LOW);

  timeSeconds += static_cast<float>(kSampleIntervalMs) / 1000.0f;
  delay(kSampleIntervalMs);
}
