# Backend API

Run locally:

```powershell
uv run --project backend python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Useful endpoints:

- `/api/judge-demo`: deterministic dashboard scenarios.
- `/api/judge-live`: short ESP32 UDP CSI probe.
- `/api/observatory-live`: compact, honest 3D Observatory state.
- `/api/ai-advice`: Gemma-backed explanation for compact Observatory state.
- `POST /api/ai-advice/interpret`: interprets one already-captured Observatory
  snapshot without performing a second ESP probe.
- `/api/calibration-coach`: Gemma-backed guidance over the existing local
  activity-label readiness and held-out evaluation report.
- `POST /api/judge-briefing`: generates an on-demand judge report from one
  posted compact Observatory snapshot and local calibration readiness.
- `POST /api/telegram-delivery`: sends one already displayed, operator-approved
  message and returns only a masked Telegram acknowledgment.

`/api/ai-advice` uses `gemma-4-31b-it` as the primary hosted model and
`gemma-4-26b-a4b-it` as fallback when `GEMINI_API_KEY` is available. Hosted
calls are bounded by `GEMINI_HTTP_TIMEOUT_MS` (default `60000`) so Gemma 4
thinking responses have time to complete while still permitting local fallback.
It sends only summarized CSI
state, never raw CSI samples or secrets. If hosted Gemma is unavailable, it
returns deterministic local rule advice.

The React live Observatory uses `/api/observatory-live` for immediate sensing
display and calls `POST /api/ai-advice/interpret` only for changed evidence
states. This keeps sensor display responsive and ensures Gemma explains the
same compact snapshot the operator saw.

For `actual_udp_probe` Observatory responses, occupied person counts are shown
as single-link candidates (`1?` / `2+?`) rather than verified counts. Live
vital numbers are hidden during motion or weak/unsuitable occupancy, and any
still-room value that passes screening is labeled as an experimental estimate.

`/api/calibration-coach` loads the existing filtering-engine label report and
sends only compact counts and evaluation output to hosted Gemma. It does not
start a capture or transmit raw CSI records.

`POST /api/judge-briefing` does not perform a live probe. Weak signal or
blocked trust remains an untrusted claim even if hosted Gemma produces more
confident wording.

`POST /api/telegram-delivery` is not an automatic alert path. It uses local
ignored Telegram credentials only after an explicit UI send action and never
returns the bot token or full chat identifier.
