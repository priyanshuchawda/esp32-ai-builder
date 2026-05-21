# Wi-Fi CSI Serial Message Protocol

This document defines the serial line CSV protocol format used to transmit signal data from the ESP32 receiver to the Python engine.

## Message Format

Each packet is printed as a single line ending with a newline (`\n`):

`timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5`

### Fields Description

| Column Index | Field Name | Data Type | Description |
|---|---|---|---|
| 0 | `timestamp` | `Integer` | Millisecond uptime of the ESP32 board, or Unix time in milliseconds |
| 1 | `rssi` | `Integer` | Received Signal Strength Indicator (typically -100 to 0 dBm) |
| 2 | `csi_0` | `Integer/Float` | Magnitude of the first subcarrier |
| 3 | `csi_1` | `Integer/Float` | Magnitude of the second subcarrier |
| 4 | `csi_2` | `Integer/Float` | Magnitude of the third subcarrier |
| 5 | `csi_3` | `Integer/Float` | Magnitude of the fourth subcarrier |
| 6 | `csi_4` | `Integer/Float` | Magnitude of the fifth subcarrier |
| 7 | `csi_5` | `Integer/Float` | Magnitude of the sixth subcarrier |

## Example Output Row

`123456,-52,14,18,21,19,80,22`

- **Timestamp**: `123456` ms
- **RSSI**: `-52` dBm
- **Subcarrier Amplitudes**: `[14, 18, 21, 19, 80, 22]`
- **Calculated Raw Signal**: `(14 + 18 + 21 + 19 + 80 + 22) / 6 = 29.0`
