# System Architecture

This document describes the pipeline architecture of the **esp32-csi-gemma-filter** local noise filtering prototype.

## Pipeline Flow Diagram

```text
+-----------------------+
|  ESP32 Dev Module     |  <-- Generates simulated or physical Wi-Fi CSI data
+-----------------------+
            |
            | (Serial COM5, 115200 baud)
            v
+-----------------------+
|  Python Serial Reader |  <-- Reads raw stream packets
+-----------------------+
            |
            | (Packets grouped in time/sample windows)
            v
+-----------------------+
|  Feature Extractor    |  <-- Computes variance, energy, outliers, RSSI stats
+-----------------------+
            |
            | (Summary stats only)
            v
+-----------------------+
|  Gemma 4 E4B Advisor  |  <-- Running locally via Ollama. Recommends filter/params
+-----------------------+
            |
            | (Strict JSON response)
            v
+-----------------------+
|   Python DSP Filter   |  <-- Applies moving average, median, Hampel, or lowpass
+-----------------------+
            |
            +------------+------------+
            |                         |
            v                         v
+-----------------------+   +------------------------+
|    Data Files CSV     |   | Headless Matplotlib    |
| (Raw, Filtered, JSON) |   | Raw vs Filtered Plot   |
+-----------------------+   +------------------------+
```

## Component Breakdown

1. **ESP32 Dev Module**: Low-power micro-controller responsible for capturing frames. Since LLM inference is highly compute-intensive and requires Gigabytes of memory, the ESP32 only captures CSI subcarrier amplitudes and transmits them directly over serial connection to the host laptop.
2. **Python Engine**:
   - **Serial Reader**: Establishes robust serial connections, reading the data byte-stream line-by-line.
   - **CSI Parser**: Extracts CSV lines into structured dictionary records, taking the average of the subcarrier amplitudes as a single scalar `raw_signal` indicator.
   - **Feature Extractor**: Dynamically groups signals into windows (default 2 seconds or 100 samples) and computes summary metrics (variance, outlier ratio, standard deviation).
   - **Gemma Advisor**: Interfaces with the local Ollama API to send statistics and obtain filter recommendations.
   - **DSP Filter**: Applies standard digital signal processing algorithms on the window values using vectorized numpy functions.
   - **Plot & Writer**: Persists CSV datasets, JSON advice, and visual PNG graphs.
