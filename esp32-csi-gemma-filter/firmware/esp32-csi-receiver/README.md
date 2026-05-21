# ESP32 CSI Receiver Firmware Skeleton

This directory contains the firmware skeleton for the Espressif ESP32 Dev Module.

## Hardware Configuration
- **Board**: Espressif ESP32 Dev Module
- **PlatformIO Board ID**: `esp32dev`
- **CPU Speed**: 240 MHz
- **RAM**: 320 KB
- **Flash**: 4 MB
- **Baud Rate**: 115200

## Milestone 1 Implementation
At this stage, the firmware runs a simulated loop that sends CSI-like dummy lines over the serial port every 100ms.
This format matches what the python-engine parser expects:
`timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5`

## Roadmap
> [!NOTE]
> **Milestone 2**: Real ESP-IDF CSI callback implementation will be added in Milestone 2 to capture actual Wi-Fi frames and extract their subcarrier magnitudes.
