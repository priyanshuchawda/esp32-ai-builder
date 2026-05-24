"""FastAPI surface for the ESP32 CSI judge dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.ai_advice import build_event_signature, query_ai_advice
from backend.calibration_coach import (
    build_calibration_snapshot,
    query_calibration_coach,
)
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
from backend.judge_briefing import query_judge_briefing
from backend.material_change import (
    MaterialChangeTracker,
    build_demo_material_change,
    fingerprint_to_amplitudes,
)
from backend.motion_cadence import build_demo_motion_cadence
from backend.observatory_state import build_observatory_state
from backend.person_count import estimate_person_count
from backend.room_state_tracker import OnlineRoomStateTracker, build_room_state
from backend.telegram_delivery import deliver_prepared_message


app = FastAPI(title="ESP32 Wi-Fi CSI Spatial Intelligence")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
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
    "material change watch",
    "motion cadence watch",
    "single-link person count",
    "quality gating",
    "Telegram alert path",
]

LIVE_ROOM_TRACKER = OnlineRoomStateTracker()
LIVE_MATERIAL_TRACKER = MaterialChangeTracker(baseline_frames=4)
INTERPRET_REQUIRED_SECTIONS = ("source", "visual", "persons", "signal", "vitals", "motion")
LOCAL_UI_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AiInterpretRequest(BaseModel):
    observatory: dict


class TelegramDeliveryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    event_signature: str = Field(min_length=1, max_length=200)


@app.get("/api/judge-demo")
def judge_demo(scenario: str = "occupied_still") -> dict:
    """Return deterministic dashboard data shaped like the live CSI pipeline."""

    selected_key = scenario.lower()
    if selected_key not in SCENARIOS:
        valid = ", ".join(sorted(SCENARIOS))
        raise HTTPException(
            status_code=400, detail=f"Unknown scenario. Valid scenarios: {valid}"
        )

    scenarios = [
        _with_room_state(build_demo_snapshot(name)) for name in sorted(SCENARIOS)
    ]
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
        (
            udp_summary,
            quality_summary,
            modes,
            occupancy,
            telemetry,
            fingerprint,
            spectrogram,
            motion_cadence,
        ) = run_udp_probe(
            bind_ip=bind_ip,
            udp_port=udp_port,
            duration_sec=duration,
            min_fps=min_fps,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=503, detail=f"Live probe failed: {type(exc).__name__}"
        ) from exc

    firmware_config = load_firmware_network_config(
        path=Path("include/wifi_credentials.h")
    )
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
    next_actions = [
        line.split(" ", 1)[1] for line in lines if line.startswith("NEXT_ACTION ")
    ]
    snapshot = _build_live_snapshot(
        occupancy,
        telemetry,
        quality_summary,
        fingerprint,
        spectrogram,
        udp_summary,
        motion_cadence,
    )

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
        "telemetry": snapshot["telemetry"],
        "fingerprint": fingerprint,
        "spectrogram": spectrogram,
        "motion_cadence": motion_cadence,
        "snapshot": snapshot,
        "next_actions": next_actions,
        "lines": lines,
    }


@app.get("/api/observatory-live")
def observatory_live(
    mode: str = Query(default="live", pattern="^(live|demo)$"),
    scenario: str = "occupied_still",
    duration: int = Query(default=3, ge=1, le=15),
    bind_ip: str = "0.0.0.0",
    udp_port: int = Query(default=5005, ge=1, le=65535),
    min_fps: float = Query(default=5.0, ge=0.1, le=100.0),
) -> dict:
    """Return a visualization-first live contract for the 3D Observatory mode."""

    if mode == "demo":
        selected_key = scenario.lower()
        if selected_key not in SCENARIOS:
            valid = ", ".join(sorted(SCENARIOS))
            raise HTTPException(
                status_code=400, detail=f"Unknown scenario. Valid scenarios: {valid}"
            )
        snapshot = _with_room_state(build_demo_snapshot(selected_key))
        state = build_observatory_state(snapshot, source="demo")
        state["title"] = "ESP32 Wi-Fi CSI Observatory"
        state["generated_at"] = datetime.now(UTC).isoformat()
        return state

    try:
        (
            udp_summary,
            quality_summary,
            _modes,
            occupancy,
            telemetry,
            fingerprint,
            spectrogram,
            motion_cadence,
        ) = run_udp_probe(
            bind_ip=bind_ip,
            udp_port=udp_port,
            duration_sec=duration,
            min_fps=min_fps,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=503, detail=f"Live probe failed: {type(exc).__name__}"
        ) from exc

    snapshot = _build_live_snapshot(
        occupancy,
        telemetry,
        quality_summary,
        fingerprint,
        spectrogram,
        udp_summary,
        motion_cadence,
    )
    firmware_config = load_firmware_network_config(
        path=Path("include/wifi_credentials.h")
    )
    config_summary = summarize_target_ip(
        target_ip=firmware_config.get("target_ip"),
        local_ip=detect_local_ip(),
        target_port=firmware_config.get("target_port"),
    )
    state = build_observatory_state(
        snapshot,
        source="actual_udp_probe",
        udp_summary=udp_summary,
        config=config_summary,
    )
    state["title"] = "ESP32 Wi-Fi CSI Observatory"
    state["generated_at"] = datetime.now(UTC).isoformat()
    state["duration_sec"] = duration
    state["udp"] = udp_summary
    return state


@app.get("/api/ai-advice")
def ai_advice(
    mode: str = Query(default="demo", pattern="^(live|demo)$"),
    scenario: str = "occupied_still",
    duration: int = Query(default=3, ge=1, le=15),
    bind_ip: str = "0.0.0.0",
    udp_port: int = Query(default=5005, ge=1, le=65535),
    min_fps: float = Query(default=5.0, ge=0.1, le=100.0),
) -> dict:
    """Return Gemma-ready explanation for compact CSI observatory state."""

    if mode == "demo":
        selected_key = scenario.lower()
        if selected_key not in SCENARIOS:
            valid = ", ".join(sorted(SCENARIOS))
            raise HTTPException(
                status_code=400, detail=f"Unknown scenario. Valid scenarios: {valid}"
            )
        snapshot = _with_room_state(build_demo_snapshot(selected_key))
        observatory = build_observatory_state(snapshot, source="demo")
    else:
        try:
            (
                udp_summary,
                quality_summary,
                _modes,
                occupancy,
                telemetry,
                fingerprint,
                spectrogram,
                motion_cadence,
            ) = run_udp_probe(
                bind_ip=bind_ip,
                udp_port=udp_port,
                duration_sec=duration,
                min_fps=min_fps,
            )
        except OSError as exc:
            raise HTTPException(
                status_code=503, detail=f"Live probe failed: {type(exc).__name__}"
            ) from exc
        snapshot = _build_live_snapshot(
            occupancy,
            telemetry,
            quality_summary,
            fingerprint,
            spectrogram,
            udp_summary,
            motion_cadence,
        )
        observatory = build_observatory_state(
            snapshot,
            source="actual_udp_probe",
            udp_summary=udp_summary,
        )

    return {
        "title": "ESP32 Wi-Fi CSI AI Advice",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": observatory["source"],
        "observatory": observatory,
        "advice": query_ai_advice(observatory),
    }


@app.post("/api/ai-advice/interpret")
def ai_advice_interpret(request: AiInterpretRequest) -> dict:
    """Interpret one already captured compact observatory state without re-probing."""

    missing = [
        section
        for section in INTERPRET_REQUIRED_SECTIONS
        if section not in request.observatory
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Observatory payload is missing required sections: {', '.join(missing)}",
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": request.observatory["source"],
        "event_signature": build_event_signature(request.observatory),
        "advice": query_ai_advice(request.observatory),
    }


@app.get("/api/calibration-coach")
def calibration_coach() -> dict:
    """Explain existing activity-label readiness without collecting new data."""

    report = build_calibration_snapshot()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "report": report,
        "advice": query_calibration_coach(report),
    }


@app.post("/api/judge-briefing")
def judge_briefing(request: AiInterpretRequest) -> dict:
    """Generate a briefing for an already displayed Observatory state."""

    missing = [
        section
        for section in INTERPRET_REQUIRED_SECTIONS
        if section not in request.observatory
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Observatory payload is missing required sections: {', '.join(missing)}",
        )
    calibration = build_calibration_snapshot()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "event_signature": build_event_signature(request.observatory),
        "calibration": calibration,
        "briefing": query_judge_briefing(request.observatory, calibration),
    }


@app.post("/api/telegram-delivery")
def telegram_delivery(
    request: TelegramDeliveryRequest, origin: str | None = Header(default=None)
) -> dict:
    """Deliver one explicitly requested, already prepared operator message."""

    if origin and urlparse(origin).hostname not in LOCAL_UI_HOSTS:
        raise HTTPException(
            status_code=403, detail="Telegram delivery is restricted to the local UI."
        )
    return deliver_prepared_message(request.message, request.event_signature)


def _build_live_snapshot(
    occupancy: dict,
    telemetry: dict,
    quality_summary: dict,
    fingerprint: dict,
    spectrogram: dict,
    udp_summary: dict,
    motion_cadence: dict,
) -> dict:
    trusted = bool(occupancy.get("trusted"))
    occupied = occupancy.get("class") == "OCCUPIED"
    snapshot_quality = dict(quality_summary)
    snapshot_quality["fps"] = udp_summary.get("fps", snapshot_quality.get("fps", 0.0))
    telemetry = _normalize_live_telemetry(
        telemetry, occupancy, fingerprint, trusted, occupied
    )
    snapshot = {
        "scenario": "live_probe",
        "source": "actual_udp_probe",
        "note": "Fresh UDP CSI probe from the ESP32 stream.",
        "telemetry": telemetry,
        "quality": snapshot_quality,
        "summary": build_power_summary(telemetry, snapshot_quality),
        "fingerprint": fingerprint,
        "spectrogram": spectrogram,
        "motion_cadence": motion_cadence,
    }
    snapshot["room_state"] = LIVE_ROOM_TRACKER.observe(snapshot)
    material_change = LIVE_MATERIAL_TRACKER.observe(
        fingerprint_to_amplitudes(fingerprint)
    )
    material_change["trusted"] = snapshot_quality.get("status") == "GOOD"
    material_change["trust_reason"] = (
        "quality_good" if material_change["trusted"] else "signal_quality_not_good"
    )
    snapshot["material_change"] = material_change
    snapshot["person_count"] = estimate_person_count(snapshot)
    return snapshot


def _normalize_live_telemetry(
    telemetry: dict,
    occupancy: dict,
    fingerprint: dict,
    trusted: bool,
    occupied: bool,
) -> dict:
    normalized = dict(telemetry or {})
    normalized["presence"] = bool(normalized.get("presence", occupied))
    normalized["resp_bpm"] = round(float(normalized.get("resp_bpm", 0.0) or 0.0), 1)
    normalized["heart_bpm"] = round(float(normalized.get("heart_bpm", 0.0) or 0.0), 1)
    normalized["fall_detected"] = bool(
        normalized.get("fall_detected", normalized.get("fall_alert", False))
    )
    normalized["variance"] = round(
        float(normalized.get("variance", fingerprint.get("spread", 0.0)) or 0.0), 2
    )
    normalized["rep_count"] = int(normalized.get("rep_count", 0) or 0)
    normalized["acceleration"] = round(
        float(normalized.get("acceleration", 0.0) or 0.0), 2
    )
    normalized["motion"] = dict(
        normalized.get("motion")
        or {
            "display_level": "STILL" if trusted and occupied else "UNSTABLE",
            "score": 0.0,
            "trusted": trusted,
        }
    )
    normalized["occupancy"] = occupancy
    return normalized


def _with_room_state(snapshot: dict) -> dict:
    snapshot["room_state"] = build_room_state(snapshot)
    snapshot["spectrogram"] = build_demo_spectrogram(snapshot)
    snapshot["material_change"] = build_demo_material_change(snapshot)
    snapshot["material_change"]["trusted"] = (
        snapshot.get("quality", {}).get("status") == "GOOD"
    )
    snapshot["material_change"]["trust_reason"] = (
        "quality_good"
        if snapshot["material_change"]["trusted"]
        else "signal_quality_not_good"
    )
    snapshot["motion_cadence"] = build_demo_motion_cadence(snapshot)
    snapshot["person_count"] = estimate_person_count(snapshot)
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
