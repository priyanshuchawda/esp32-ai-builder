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

`/api/ai-advice` uses `gemma-4-31b-it` as the primary hosted model and
`gemma-4-26b-a4b-it` as fallback when `GEMINI_API_KEY` is available. It sends
only summarized CSI state, never raw CSI samples or secrets. If hosted Gemma is
unavailable, it returns deterministic local rule advice.
