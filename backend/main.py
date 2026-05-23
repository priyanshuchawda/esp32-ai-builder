"""FastAPI surface for the ESP32 CSI judge dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.csi_demo_simulator import SCENARIOS, build_demo_snapshot
from backend.csi_power_summary import build_power_summary
from backend.csi_spectrogram import build_demo_spectrogram
from backend.esp_live_probe import (
    build_probe_lines,
    detect_local_ip,
    load_firmware_network_config,
    run_udp_probe,
    summarize_target_ip,
)
from backend.room_state_tracker import OnlineRoomStateTracker, build_room_state


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

LIVE_ROOM_TRACKER = OnlineRoomStateTracker()


@app.get("/api/judge-demo")
def judge_demo(scenario: str = "occupied_still") -> dict:
    """Return deterministic dashboard data shaped like the live CSI pipeline."""

    selected_key = scenario.lower()
    if selected_key not in SCENARIOS:
        valid = ", ".join(sorted(SCENARIOS))
        raise HTTPException(status_code=400, detail=f"Unknown scenario. Valid scenarios: {valid}")

    scenarios = [_with_room_state(build_demo_snapshot(name)) for name in sorted(SCENARIOS)]
    live = _with_room_state(build_demo_snapshot("weak_live_stream"))
    live["source"] = "simulated_fallback"
    live["note"] = "Live COM5 capture is available through backend/esp_live_probe.py."

    return {
        "title": "ESP32 Wi-Fi CSI Spatial Intelligence",
        "generated_at": datetime.now(UTC).isoformat(),
        "selected": _with_room_state(build_demo_snapshot(selected_key)),
        "scenarios": scenarios,
        "live": live,
        "pipeline": PIPELINE,
        "capabilities": CAPABILITIES,
    }


@app.get("/api/judge-live")
def judge_live(
    duration: int = Query(default=3, ge=1, le=15),
    bind_ip: str = "0.0.0.0",
    udp_port: int = Query(default=5005, ge=1, le=65535),
    min_fps: float = Query(default=5.0, ge=0.1, le=100.0),
) -> dict:
    """Run a short real UDP CSI probe and return dashboard-ready live data."""

    try:
        udp_summary, quality_summary, modes, occupancy, fingerprint, spectrogram = run_udp_probe(
            bind_ip=bind_ip,
            udp_port=udp_port,
            duration_sec=duration,
            min_fps=min_fps,
        )
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Live probe failed: {type(exc).__name__}") from exc

    firmware_config = load_firmware_network_config(path=Path("include/wifi_credentials.h"))
    config_summary = summarize_target_ip(
        target_ip=firmware_config.get("target_ip"),
        local_ip=detect_local_ip(),
        target_port=firmware_config.get("target_port"),
    )
    lines = build_probe_lines(
        issue=73,
        duration_sec=duration,
        config_summary=config_summary,
        udp_summary=udp_summary,
        quality_summary=quality_summary,
        modes=modes,
        fingerprint=fingerprint,
        occupancy=occupancy,
    )
    overall_status = _line_value(lines[0], "status") or "UNKNOWN"
    next_actions = [line.split(" ", 1)[1] for line in lines if line.startswith("NEXT_ACTION ")]
    snapshot = _build_live_snapshot(occupancy, quality_summary, fingerprint, spectrogram, udp_summary)

    return {
        "title": "ESP32 Wi-Fi CSI Spatial Intelligence",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "actual_udp_probe",
        "duration_sec": duration,
        "overall_status": overall_status,
        "udp": udp_summary,
        "quality": quality_summary,
        "modes": {str(mode): count for mode, count in modes.items()},
        "config": config_summary,
        "occupancy": occupancy,
        "fingerprint": fingerprint,
        "spectrogram": spectrogram,
        "snapshot": snapshot,
        "next_actions": next_actions,
        "lines": lines,
    }


def _build_live_snapshot(
    occupancy: dict,
    quality_summary: dict,
    fingerprint: dict,
    spectrogram: dict,
    udp_summary: dict,
) -> dict:
    trusted = bool(occupancy.get("trusted"))
    occupied = occupancy.get("class") == "OCCUPIED"
    snapshot_quality = dict(quality_summary)
    snapshot_quality["fps"] = udp_summary.get("fps", snapshot_quality.get("fps", 0.0))
    telemetry = {
        "presence": occupied,
        "resp_bpm": 0.0,
        "heart_bpm": 0.0,
        "fall_detected": False,
        "variance": round(float(fingerprint.get("spread", 0.0)), 2),
        "motion": {
            "display_level": "STILL" if trusted and occupied else "UNSTABLE",
            "score": 0.0,
            "trusted": trusted,
        },
        "occupancy": occupancy,
    }
    snapshot = {
        "scenario": "live_probe",
        "source": "actual_udp_probe",
        "note": "Fresh UDP CSI probe from the ESP32 stream.",
        "telemetry": telemetry,
        "quality": snapshot_quality,
        "summary": build_power_summary(telemetry, snapshot_quality),
        "fingerprint": fingerprint,
        "spectrogram": spectrogram,
    }
    snapshot["room_state"] = LIVE_ROOM_TRACKER.observe(snapshot)
    return snapshot


def _with_room_state(snapshot: dict) -> dict:
    snapshot["room_state"] = build_room_state(snapshot)
    snapshot["spectrogram"] = build_demo_spectrogram(snapshot)
    return snapshot


def _line_value(line: str, key: str) -> str | None:
    prefix = f"{key}="
    for part in line.split():
        if part.startswith(prefix):
            return part.removeprefix(prefix)
    return None


def main() -> None:
    print("Run with: uvicorn backend.main:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    main()
