# ESP32 AI Builder

ESP32 + AI workspace for Wi-Fi CSI sensing experiments, a Python Gemma filtering engine, a FastAPI backend scaffold, and a React/Vite frontend scaffold.

## Main Components

- `esp32-csi-gemma-filter/`: Python CSI filtering pipeline with hosted Gemma 4 advisor support through the Gemini API, optional Ollama fallback, and Telegram human-presence alerts.
- `src/`, `include/`, `lib/`, `test/`, `platformio.ini`: PlatformIO ESP32 firmware workspace that streams parser-compatible real Wi-Fi CSI rows when credentials are present, with a simulated fallback.
- `backend/`: Python backend scaffold managed with `uv`.
- `frontend/`: Vite React frontend scaffold.

## Local Secrets

Do not commit real tokens. Copy `esp32-csi-gemma-filter/.env.example` to a local `.env` file and fill:

- `GEMINI_API_KEY`: Gemini API key from Google AI Studio for hosted Gemma 4.
- `GEMINI_GEMMA_MODEL`: Primary hosted advisor model, defaults to `gemma-4-31b-it`.
- `GEMINI_GEMMA_FALLBACK_MODEL`: Hosted retry model, defaults to `gemma-4-26b-a4b-it`.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token from BotFather.
- `TELEGRAM_CHAT_ID`: Your chat ID after you send `/start` to the bot.
- `HUMAN_ALERT_ENABLED=true`: Enables Telegram alerts when human presence is detected.

## Calibration

Record labeled CSI feature windows for later activity classification:

```powershell
cd esp32-csi-gemma-filter
uv run --with-requirements python-engine/requirements.txt python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 30 --label walking --advisor-provider rules
```

Labeled capture skips sparse windows by default unless they have at least 10 CSI
samples. Override with `--label-min-samples` only when you intentionally want
short windows.

Summarize collected labels and run the local baseline evaluator:

```powershell
uv run --with-requirements python-engine/requirements.txt python python-engine/calibration_report.py
```

The report includes readiness guidance for the default target labels:
`empty`, `sitting`, and `walking`.

Build the local activity model from collected labels:

```powershell
uv run --with-requirements python-engine/requirements.txt python python-engine/activity_classifier.py
```

Enable live activity prediction during a run after enough labels are collected:

```powershell
uv run --with-requirements python-engine/requirements.txt python python-engine/app.py --mode serial --port COM5 --baud 115200 --duration 30 --activity-classifier --advisor-provider rules
```

## Test

Active backend tests should be run from the repository root. The root
`pytest.ini` intentionally scopes collection to `backend/` so archived RuView
and legacy experiment trees are not collected by accident.

```powershell
uv run --project backend pytest -q
```

Legacy Gemma-filter tests can still be run directly when working in that
subproject:

```powershell
cd esp32-csi-gemma-filter
uv run --with-requirements python-engine/requirements.txt pytest tests
```
