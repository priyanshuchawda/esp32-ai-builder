# esp32-csi-gemma-filter

Gemma 4 E4B assisted local Wi-Fi CSI noise filtering using ESP32 and Python.

## Project Goal
This project builds a local Wi-Fi Channel State Information (CSI) noise-filtering pipeline. It uses an ESP32 micro-controller to capture raw radio signals, a Python processing engine on a laptop to analyze signal windows, and a locally-hosted Gemma 4 E4B model (via Ollama) as a high-level Advisor/Controller that determines the best filtering configuration dynamically.

## Architecture

```text
+--------------+                   +---------------+
|  ESP32 Board | --(COM5 Serial)-->| Python Engine | <--[Summary Stats Only]--> Local Gemma 4 E4B
+--------------+                   +---------------+                            (via Ollama API)
                                           |
                                           +---> Filters Signal (Numpy)
                                           |
                                           v
                                   Save CSVs, JSON, & Plots
```

### Design Justifications

* **Why ESP32?**: The ESP32 is a cheap, low-power micro-controller with full Wi-Fi capability. It supports dumping raw OFDM channel frequency response (CSI) subcarrier information, making it ideal for wireless sensing.
* **Why Gemma on Laptop?**: A local LLM requires gigabytes of RAM and heavy floating-point operations. The ESP32 has only 320 KB RAM and a 240 MHz dual-core CPU, making it incapable of running Gemma. Running Gemma locally on the laptop ensures privacy and offline capability.
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

### 2. Ollama & Gemma Setup
1. Download and install [Ollama](https://ollama.com/) for Windows.
2. Pull and run the required model:
   ```bash
   ollama run gemma4:e4b
   ```
3. Keep Ollama running in the background. The python engine connects to `http://localhost:11434/api/chat`.

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

### C. Telegram Human-Presence Alerts
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
