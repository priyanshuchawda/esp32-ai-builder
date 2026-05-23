"""FastAPI surface for the ESP32 CSI judge dashboard."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.csi_demo_simulator import SCENARIOS, build_demo_snapshot


app = FastAPI(title="ESP32 Wi-Fi CSI Spatial Intelligence")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

PIPELINE = [
    {
        "label": "ESP32 DevKit V1",
        "detail": "Captures Wi-Fi CSI amplitude changes over serial or UDP.",
        "state": "hardware",
    },
    {
        "label": "CSI packet stream",
        "detail": "Filters boot noise, mixed subcarrier frames, FPS drops, and RSSI instability.",
        "state": "signal",
    },
    {
        "label": "RuView DSP filters",
        "detail": "Summarizes occupancy, motion level, fall events, vitals, and signal confidence.",
        "state": "analysis",
    },
    {
        "label": "Gemma advisor",
        "detail": "Adds explainable room-state recommendations when API credentials are present.",
        "state": "ai",
    },
    {
        "label": "Telegram + dashboard",
        "detail": "Shows live room status and sends cooldown-protected human-presence alerts.",
        "state": "output",
    },
]

CAPABILITIES = [
    "empty-room baseline",
    "human presence",
    "still occupancy",
    "walking motion",
    "fall-event simulation",
    "CSI fingerprint",
    "quality gating",
    "Telegram alert path",
]


@app.get("/api/judge-demo")
def judge_demo(scenario: str = "occupied_still") -> dict:
    """Return deterministic dashboard data shaped like the live CSI pipeline."""

    selected_key = scenario.lower()
    if selected_key not in SCENARIOS:
        valid = ", ".join(sorted(SCENARIOS))
        raise HTTPException(status_code=400, detail=f"Unknown scenario. Valid scenarios: {valid}")

    scenarios = [build_demo_snapshot(name) for name in sorted(SCENARIOS)]
    live = build_demo_snapshot("weak_live_stream")
    live["source"] = "simulated_fallback"
    live["note"] = "Live COM5 capture is available through backend/esp_live_probe.py."

    return {
        "title": "ESP32 Wi-Fi CSI Spatial Intelligence",
        "generated_at": datetime.now(UTC).isoformat(),
        "selected": build_demo_snapshot(selected_key),
        "scenarios": scenarios,
        "live": live,
        "pipeline": PIPELINE,
        "capabilities": CAPABILITIES,
    }


def main() -> None:
    print("Run with: uvicorn backend.main:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    main()
