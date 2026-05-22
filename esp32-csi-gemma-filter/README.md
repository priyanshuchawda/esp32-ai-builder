# esp32-csi-gemma-filter

Gemma 4 assisted Wi-Fi CSI noise filtering using ESP32, Python, and the Gemini API.

## Project Goal
This project builds a Wi-Fi Channel State Information (CSI) noise-filtering pipeline. It uses an ESP32 micro-controller to capture raw radio signals, a Python processing engine on a laptop to analyze signal windows, and hosted Gemma 4 through the Gemini API as a high-level Advisor/Controller that determines the best filtering configuration dynamically.

## Architecture

```text
+--------------+                   +---------------+
|  ESP32 Board | --(COM5 Serial)-->| Python Engine | <--[Summary Stats Only]--> Gemma 4
+--------------+                   +---------------+                            (Gemini API)
                                           |
                                           +---> Filters Signal (Numpy)
                                           |
                                           v
                                   Save CSVs, JSON, & Plots
```

### Design Justifications

* **Why ESP32?**: The ESP32 is a cheap, low-power micro-controller with full Wi-Fi capability. It supports dumping raw OFDM channel frequency response (CSI) subcarrier information, making it ideal for wireless sensing.
* **Why hosted Gemma?**: A local LLM requires gigabytes of RAM and heavy floating-point operations. The ESP32 has only 320 KB RAM and a 240 MHz dual-core CPU, making it incapable of running Gemma. The Gemini API gives the Python engine hosted access to stronger Gemma 4 models without running a local model server.
* **Why Advisor/Controller split?**: Sending every high-frequency CSI sample directly to a local LLM would create a bottleneck due to latency. Instead, Python computes window statistics (variance, outlier ratio, standard deviation) and queries Gemma only once per window. Python then performs the actual mathematical DSP filtering on the full high-frequency signal in milliseconds using numpy.

---

## Setup Instructions

### 1. Python Environment Setup
Install Python 3.13 (or compatible) on your laptop.

```bash
# Navigate to python-engine folder
cd python-engine

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Gemini API Gemma Setup
1. Create a Gemini API key in Google AI Studio.
2. Copy `.env.example` to `.env`.
3. Set:
   ```env
   GEMMA_ADVISOR_PROVIDER=gemini
   GEMINI_API_KEY=
   GEMINI_GEMMA_MODEL=gemma-4-31b-it
   GEMINI_THINKING_LEVEL=high
   ```

The default hosted model is `gemma-4-31b-it`. You can switch to `gemma-4-26b-a4b-it` by changing `GEMINI_GEMMA_MODEL`.

### 3. Optional Local Ollama Fallback
If you want to use a local Ollama server instead of the Gemini API, set:

```env
GEMMA_ADVISOR_PROVIDER=ollama
OLLAMA_TIMEOUT_SECONDS=120
```

The local engine uses `gemma4:e2b` by default.

---

## How to Run

### A. Simulated Mode (Default)
Runs the filtering pipeline using noisy simulated signals. This allows testing even when the ESP32 is not connected or flashed.
```bash
python python-engine/app.py --mode simulate --duration 20
```

### B. Serial Mode
Connects to the ESP32 Dev Module and reads live signals.
```bash
python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 20
```

The root PlatformIO firmware emits parser-compatible rows:

```text
timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5
```

To enable real Wi-Fi CSI capture, copy `include/wifi_credentials.example.h` to
`include/wifi_credentials.h`, fill `WIFI_SSID` and `WIFI_PASSWORD`, then upload
the firmware. If that private file is absent, the firmware keeps using a
simulated CSI-like stream so the Python pipeline still works.

Real CSI frames require Wi-Fi traffic on the connected network. If no rows appear
after flashing the real CSI mode, keep the ESP32 close to the router and create
traffic from another device on the same network, such as a continuous ping or
video stream.

Classic ESP32 boards only support 2.4 GHz Wi-Fi. Use the 2.4 GHz SSID for
`WIFI_SSID`; 5 GHz-only networks will not connect. Firmware status lines start
with `#`, and the firmware automatically falls back to simulated CSV rows if
Wi-Fi or CSI frames are unavailable.

### C. Labeled Calibration Data
Use `--label` to record per-window feature rows for future activity
classification experiments:

```bash
python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 30 --label empty --advisor-provider rules
python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 30 --label walking --advisor-provider rules
python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 30 --label sitting --advisor-provider rules
```

Labels are normalized to safe filenames and appended as JSONL under
`python-engine/data/labels/<label>.jsonl`.
The `rules` advisor avoids slow network calls while collecting calibration data.

After collecting at least two labels, summarize the dataset and run the local
nearest-centroid baseline:

```bash
python python-engine/calibration_report.py
```

The report includes a readiness block for the default labels `empty`,
`sitting`, and `walking`, including how many rows are still needed per label.

Build the local activity model from the same labels:

```bash
python python-engine/activity_classifier.py
```

Once at least two labels have enough rows, enable live prediction during a run:

```bash
python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 30 --activity-classifier --advisor-provider rules
```

### D. Telegram Human-Presence Alerts
Copy `.env.example` to `.env`, then set:

```env
HUMAN_ALERT_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

The app sends a Telegram message when a processed CSI window crosses the configured human-presence thresholds. Alerts are rate-limited with `HUMAN_ALERT_COOLDOWN_SEC`.

---

## Expected Output Files

Each session creates unique output files saved under `python-engine/data/`:
1. **Raw CSV**: `python-engine/data/raw/session_<timestamp>_raw.csv` (Original captured data)
2. **Filtered CSV**: `python-engine/data/filtered/session_<timestamp>_filtered.csv` (Resulting filtered signals and applied filters)
3. **Decisions Log**: `python-engine/data/decisions/session_<timestamp>_decision.json` (Advisor recommendations and reasons)
4. **Visual Graph**: `python-engine/data/plots/session_<timestamp>_raw_vs_filtered.png` (PNG comparison plot)

---

## Future Roadmap
1. **Milestone 2**: Capture real physical ESP32 CSI packets using Wi-Fi frame callbacks.
2. **Milestone 3**: Implement human presence detection based on subcarrier amplitude variance.
3. **Milestone 4**: Enhance filtering algorithms with adaptive wavelet transforms.
4. **Milestone 5**: Real-time activity detection and wireless pose estimation experiments.
