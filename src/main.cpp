#include <Arduino.h>
#include <math.h>

#if __has_include("wifi_credentials.h")
#include "wifi_credentials.h"
#define HAS_WIFI_CREDENTIALS 1
#else
#define HAS_WIFI_CREDENTIALS 0
#endif

#if HAS_WIFI_CREDENTIALS
#include <WiFi.h>
#include "esp_wifi.h"
#endif

namespace {
constexpr uint32_t kBaudRate = 115200;
constexpr uint32_t kSampleIntervalMs = 100;
constexpr int kStatusLedPin = 2;
constexpr int kCsiBins = 6;

struct CsiSample {
  int64_t timestampMs;
  int rssi;
  int bins[kCsiBins];
  uint32_t sequence;
};

volatile bool g_hasRealCsi = false;
CsiSample g_latestSample = {};
portMUX_TYPE g_sampleMux = portMUX_INITIALIZER_UNLOCKED;

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

void printCsvSample(const CsiSample &sample) {
  Serial.printf("%lld,%d,%d,%d,%d,%d,%d,%d\n",
                sample.timestampMs,
                sample.rssi,
                sample.bins[0],
                sample.bins[1],
                sample.bins[2],
                sample.bins[3],
                sample.bins[4],
                sample.bins[5]);
}

void printSimulatedSample() {
  static float timeSeconds = 0.0f;

  const float baseline = 20.0f + 5.0f * sinf(2.0f * PI * 0.05f * timeSeconds);
  const float noise = randomFloat(-1.5f, 1.5f);
  const bool hasSpike = (esp_random() % 100U) < 5U;
  const float spike = hasSpike ? ((esp_random() % 2U) == 0U ? 30.0f : -25.0f) : 0.0f;
  const float signal = baseline + noise + spike;

  CsiSample sample = {};
  sample.timestampMs = static_cast<int64_t>(millis());
  sample.rssi = -50 + static_cast<int>(0.2f * signal) +
                static_cast<int>(esp_random() % 3U) - 1;
  for (int i = 0; i < kCsiBins; ++i) {
    sample.bins[i] = clampCsi(signal + randomFloat(-2.0f, 2.0f));
  }

  printCsvSample(sample);
  timeSeconds += static_cast<float>(kSampleIntervalMs) / 1000.0f;
}

#if HAS_WIFI_CREDENTIALS
void csiCallback(void *, wifi_csi_info_t *data) {
  if (data == nullptr || data->buf == nullptr || data->len < 2) {
    return;
  }

  int accum[kCsiBins] = {0};
  int counts[kCsiBins] = {0};
  const int pairCount = data->len / 2;

  for (int pairIndex = 0; pairIndex < pairCount; ++pairIndex) {
    const int imag = data->buf[pairIndex * 2];
    const int real = data->buf[pairIndex * 2 + 1];
    const int magnitude = static_cast<int>(sqrtf(real * real + imag * imag));
    const int bin = (pairIndex * kCsiBins) / pairCount;
    accum[bin] += magnitude;
    counts[bin] += 1;
  }

  CsiSample sample = {};
  sample.timestampMs = static_cast<int64_t>(millis());
  sample.rssi = data->rx_ctrl.rssi;
  for (int i = 0; i < kCsiBins; ++i) {
    sample.bins[i] = counts[i] > 0 ? max(1, accum[i] / counts[i]) : 1;
  }

  portENTER_CRITICAL_ISR(&g_sampleMux);
  sample.sequence = g_latestSample.sequence + 1;
  g_latestSample = sample;
  g_hasRealCsi = true;
  portEXIT_CRITICAL_ISR(&g_sampleMux);
}

bool startRealCsiCapture() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < 15000U) {
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  wifi_csi_config_t csiConfig = {};
  csiConfig.lltf_en = true;
  csiConfig.htltf_en = true;
  csiConfig.stbc_htltf2_en = true;
  csiConfig.ltf_merge_en = true;
  csiConfig.channel_filter_en = false;
  csiConfig.manu_scale = false;
  csiConfig.shift = 0;

  if (esp_wifi_set_csi_rx_cb(csiCallback, nullptr) != ESP_OK) {
    return false;
  }
  if (esp_wifi_set_csi_config(&csiConfig) != ESP_OK) {
    return false;
  }
  if (esp_wifi_set_promiscuous(true) != ESP_OK) {
    return false;
  }
  if (esp_wifi_set_csi(true) != ESP_OK) {
    return false;
  }

  return true;
}
#endif
}  // namespace

void setup() {
  Serial.begin(kBaudRate);
  pinMode(kStatusLedPin, OUTPUT);
  delay(500);

#if HAS_WIFI_CREDENTIALS
  if (!startRealCsiCapture()) {
    g_hasRealCsi = false;
  }
#endif
}

void loop() {
  static bool ledState = false;
  static uint32_t lastPrintedSequence = 0;

#if HAS_WIFI_CREDENTIALS
  CsiSample sample = {};
  bool hasNewRealSample = false;
  portENTER_CRITICAL(&g_sampleMux);
  if (g_hasRealCsi && g_latestSample.sequence != lastPrintedSequence) {
    sample = g_latestSample;
    lastPrintedSequence = g_latestSample.sequence;
    hasNewRealSample = true;
  }
  portEXIT_CRITICAL(&g_sampleMux);

  if (hasNewRealSample) {
    printCsvSample(sample);
  } else {
    delay(10);
  }
#else
  printSimulatedSample();
  delay(kSampleIntervalMs);
#endif

  ledState = !ledState;
  digitalWrite(kStatusLedPin, ledState ? HIGH : LOW);
}
