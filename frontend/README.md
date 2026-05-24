# ESP32 CSI Observatory Frontend

React/Vite interface for the ESP32 Wi-Fi CSI judge demo. The default experience
includes the operational dashboard and the full-screen Observatory view.

## Views

- **Dashboard**: signal quality, occupancy, cadence, room state, and live probe
  summaries.
- **Observatory**: Three.js RF-field visualization driven by compact CSI state,
  not camera pose or true DensePose.
- **Gemma advice panel**: uses `/api/ai-advice` to show the hosted Gemma model
  used, fallback status, judge-safe interpretation, recommended next action,
  and a Telegram-safe prepared message.
- **Evidence timeline**: in Live ESP mode, records up to five changed ESP
  inference states and their matching Gemma interpretations.
- **Gemma calibration coach**: on explicit refresh, summarizes existing
  labeled-window readiness and evaluation accuracy, then suggests the next
  capture label without creating data.
- **Judge briefing**: after a Live ESP snapshot, explicitly generates a
  bounded Gemma report from that captured evidence and calibration status.

The live view only claims an activity state when the backend trust gate allows
it. Weak data renders a guarded explanation instead of a human/activity claim.
Live person-count values are candidate indicators rather than verified counts;
vital numbers are hidden during movement or weak signal and otherwise labeled
as experimental estimates.

## Start

Start the backend from the repository root:

```powershell
uv run --project backend python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
cd frontend
$env:VITE_API_BASE='http://127.0.0.1:8000'
pnpm.cmd run dev --host 127.0.0.1 --port 5177
```

Open `http://127.0.0.1:5177`, choose **Observatory**, then choose **Live ESP**
for a three-second real UDP capture. The scene updates from the ESP snapshot
first; a hosted Gemma interpretation is then attached to each changed
evidence state.

## Validate

```powershell
pnpm.cmd run test
pnpm.cmd run lint
pnpm.cmd run build
```
