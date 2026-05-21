# ESP32 AI Builder

ESP32 + local AI workspace for Wi-Fi CSI sensing experiments, a Python Gemma/Ollama filtering engine, a FastAPI backend scaffold, and a React/Vite frontend scaffold.

## Main Components

- `esp32-csi-gemma-filter/`: Python CSI filtering pipeline with Ollama `gemma4:e2b` advisor support and Telegram human-presence alerts.
- `src/`, `include/`, `lib/`, `test/`, `platformio.ini`: PlatformIO ESP32 firmware workspace.
- `backend/`: Python backend scaffold managed with `uv`.
- `frontend/`: Vite React frontend scaffold.

## Local Secrets

Do not commit real tokens. Copy `esp32-csi-gemma-filter/.env.example` to a local `.env` file and fill:

- `TELEGRAM_BOT_TOKEN`: Telegram bot token from BotFather.
- `TELEGRAM_CHAT_ID`: Your chat ID after you send `/start` to the bot.
- `HUMAN_ALERT_ENABLED=true`: Enables Telegram alerts when human presence is detected.

## Test

```powershell
cd esp32-csi-gemma-filter
uv run --with-requirements python-engine/requirements.txt pytest tests
```
