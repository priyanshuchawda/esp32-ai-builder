#pragma once

// Copy this file to include/wifi_credentials.h and fill your local Wi-Fi details.
// include/wifi_credentials.h is ignored by Git.
#define WIFI_SSID "your_wifi_ssid"
#define WIFI_PASSWORD "your_wifi_password"

// Destination computer's IP address and UDP port running the Streamlit app
#define TARGET_IP "192.168.1.100"
#define TARGET_PORT 5005

// Optional: lock the ESP32 to a specific 2.4 GHz AP if your router has
// multiple APs with the same SSID.
// #define WIFI_CHANNEL 1
// #define WIFI_BSSID {0x00, 0x11, 0x22, 0x33, 0x44, 0x55}

// Unique identifier for this CSI node (1-255)
#define NODE_ID 1

