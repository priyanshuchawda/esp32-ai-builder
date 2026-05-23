#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_wifi.h"

// Check if credentials file exists, otherwise use defaults
#if __has_include("wifi_credentials.h")
#include "wifi_credentials.h"
#define HAS_WIFI_CREDENTIALS 1
#else
#define HAS_WIFI_CREDENTIALS 0
#endif

// Fallback configuration if wifi_credentials.h is not found or missing defines
#ifndef WIFI_SSID
#define WIFI_SSID "your_wifi_ssid"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "your_wifi_password"
#endif
#ifndef TARGET_IP
#define TARGET_IP "192.168.1.100"
#endif
#ifndef TARGET_PORT
#define TARGET_PORT 5005
#endif
#ifndef NODE_ID
#define NODE_ID 1
#endif

namespace {
constexpr uint32_t kBaudRate = 115200;
constexpr int kStatusLedPin = 2; // Onboard LED for DevKit V1
constexpr int kCsiBins = 6;      // For serial CSV fallback (compatible with old engine)

// UDP target settings
const char* kTargetIp = TARGET_IP;
const uint16_t kTargetPort = TARGET_PORT;
const uint8_t kNodeId = NODE_ID;

WiFiUDP g_udp;
uint32_t g_sequence = 0;
unsigned long g_lastProcessMs = 0;
constexpr unsigned long kMinProcessIntervalMs = 20; // 50 Hz max sample rate to prevent network/CPU overload

// Latest sample statistics for serial output
struct CsiSample {
  int64_t timestampMs;
  int rssi;
  int bins[kCsiBins];
  uint32_t sequence;
};

volatile bool g_hasRealCsi = false;
CsiSample g_latestSample = {};
portMUX_TYPE g_sampleMux = portMUX_INITIALIZER_UNLOCKED;

void printStatus(const char *message) {
  Serial.print("# ");
  Serial.println(message);
}

// Function to construct and send ADR-018 binary packet over UDP
void sendCsiUdp(wifi_csi_info_t *data) {
  if (data == nullptr || data->buf == nullptr || data->len == 0) {
    return;
  }

  uint8_t n_antennas = 1;
  uint16_t iq_len = data->len;
  uint16_t n_subcarriers = iq_len / 2; // 1 byte I, 1 byte Q per subcarrier

  // Derive frequency from channel number
  uint8_t channel = data->rx_ctrl.channel;
  uint32_t freq_mhz = 0;
  if (channel >= 1 && channel <= 13) {
    freq_mhz = 2412 + (channel - 1) * 5;
  } else if (channel == 14) {
    freq_mhz = 2484;
  }

  // Build the 20-byte ADR-018 header
  // Structure:
  // [0..3]   Magic: 0xC5110001 (LE u32)
  // [4]      Node ID (u8)
  // [5]      Antennas (u8)
  // [6..7]   Number of subcarriers (LE u16)
  // [8..11]  Frequency MHz (LE u32)
  // [12..15] Sequence number (LE u32)
  // [16]     RSSI (i8)
  // [17]     Noise floor (i8)
  // [18..19] Reserved (LE u16)
  uint8_t header[20];
  uint32_t magic = 0xC5110001;
  
  memcpy(&header[0], &magic, 4);
  header[4] = kNodeId;
  header[5] = n_antennas;
  memcpy(&header[6], &n_subcarriers, 2);
  memcpy(&header[8], &freq_mhz, 4);
  
  portENTER_CRITICAL_ISR(&g_sampleMux);
  uint32_t seq = g_sequence++;
  portEXIT_CRITICAL_ISR(&g_sampleMux);
  
  memcpy(&header[12], &seq, 4);
  header[16] = (uint8_t)data->rx_ctrl.rssi;
  header[17] = (uint8_t)data->rx_ctrl.noise_floor;
  header[18] = 0;
  header[19] = 0;

  // Stream packet via UDP
  g_udp.beginPacket(kTargetIp, kTargetPort);
  g_udp.write(header, sizeof(header));
  g_udp.write((const uint8_t*)data->buf, iq_len);
  g_udp.endPacket();
}

// WiFi CSI Callback
void csiCallback(void *, wifi_csi_info_t *data) {
  if (data == nullptr || data->buf == nullptr || data->len < 2) {
    return;
  }

  // Rate limiter (50 Hz maximum)
  unsigned long now = millis();
  if (now - g_lastProcessMs < kMinProcessIntervalMs) {
    return;
  }
  g_lastProcessMs = now;

  // 1. Send the binary packet over UDP
  sendCsiUdp(data);

  // 2. Process for local Serial CSV output
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
  sample.timestampMs = static_cast<int64_t>(now);
  sample.rssi = data->rx_ctrl.rssi;
  for (int i = 0; i < kCsiBins; ++i) {
    sample.bins[i] = counts[i] > 0 ? max(1, accum[i] / counts[i]) : 1;
  }

  portENTER_CRITICAL_ISR(&g_sampleMux);
  sample.sequence = g_sequence; // synced sequence
  g_latestSample = sample;
  g_hasRealCsi = true;
  portEXIT_CRITICAL_ISR(&g_sampleMux);
}

bool startRealCsiCapture() {
  printStatus("WIFI_CONNECTING");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < 15000) {
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    printStatus("WIFI_CONNECT_FAILED");
    return false;
  }
  
  Serial.printf("# WIFI_CONNECTED IP: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("# STREAMING UDP TO %s:%d (Node: %u)\n", kTargetIp, kTargetPort, kNodeId);

  // Enable promiscuous mode to receive callbacks on all packets
  wifi_csi_config_t csiConfig = {};
  csiConfig.lltf_en = true;
  csiConfig.htltf_en = true;
  // Keep STBC HT-LTF disabled on ESP32 DevKit V1 to reduce CSI frame-length
  // switching between 64/128/192 bins on ordinary router traffic.
  csiConfig.stbc_htltf2_en = false;
  csiConfig.ltf_merge_en = true;
  csiConfig.channel_filter_en = false;
  csiConfig.manu_scale = false;
  csiConfig.shift = 0;

  if (esp_wifi_set_csi_rx_cb(csiCallback, nullptr) != ESP_OK) {
    printStatus("REAL_CSI_CALLBACK_FAILED");
    return false;
  }
  if (esp_wifi_set_csi_config(&csiConfig) != ESP_OK) {
    printStatus("REAL_CSI_CONFIG_FAILED");
    return false;
  }
  if (esp_wifi_set_promiscuous(true) != ESP_OK) {
    printStatus("REAL_CSI_PROMISCUOUS_FAILED");
    return false;
  }
  
  // Keep the stream on management frames only. Data frames increased frame
  // length switching and RSSI spread during live DevKit V1 tests.
  wifi_promiscuous_filter_t filt = {
      .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT,
  };
  if (esp_wifi_set_promiscuous_filter(&filt) != ESP_OK) {
    printStatus("PROMISCUOUS_FILTER_FAILED");
  }

  if (esp_wifi_set_csi(true) != ESP_OK) {
    printStatus("REAL_CSI_ENABLE_FAILED");
    return false;
  }

  printStatus("REAL_CSI_ENABLED_STREAMING");
  return true;
}
} // namespace

void setup() {
  Serial.begin(kBaudRate);
  pinMode(kStatusLedPin, OUTPUT);
  delay(1000);

  printStatus("STARTING_ESP32_CSI_NODE");

  if (!startRealCsiCapture()) {
    printStatus("RUNNING_WITHOUT_WIFI_CSI");
  }
}

void loop() {
  static bool ledState = false;
  static uint32_t lastPrintedSequence = 0;

  // If WiFi drops, try to reconnect
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(kStatusLedPin, LOW);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    delay(2000);
    return;
  }

  // Toggle status LED to show activity
  ledState = !ledState;
  digitalWrite(kStatusLedPin, ledState ? HIGH : LOW);

  // Serial CSV print loop
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
    // timestamp, rssi, csi_0..5
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

  delay(20);
}
