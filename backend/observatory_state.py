"""Projection layer for the judge-facing Observatory visualization.

This module converts real CSI summaries into display states. It deliberately
describes avatar state as inferred activity, not camera-grade pose or DensePose.
"""

from __future__ import annotations

from typing import Any


TRUTH_LABEL = "visualization_only_not_densepose"
CLAIM = "CSI-inferred activity visualization"


def build_observatory_state(
    snapshot: dict[str, Any],
    *,
    source: str,
    udp_summary: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact, honest contract for the 3D Observatory frontend."""

    telemetry = snapshot.get("telemetry") or {}
    quality = snapshot.get("quality") or {}
    occupancy = telemetry.get("occupancy") or {}
    motion = telemetry.get("motion") or {}
    cadence = snapshot.get("motion_cadence") or {}
    person_count = snapshot.get("person_count") or _unknown_person_count()

    visual = _visual_projection(telemetry, quality, occupancy, motion, cadence)

    return {
        "source": source,
        "truth_label": TRUTH_LABEL,
        "visual": visual,
        "persons": person_count,
        "signal": {
            "quality": str(quality.get("status") or "UNKNOWN"),
            "fps": round(float(quality.get("fps", 0.0) or 0.0), 2),
            "packets": int((udp_summary or {}).get("packets", 0) or 0),
            "reasons": list(quality.get("reasons") or []),
        },
        "vitals": {
            "resp_bpm": round(float(telemetry.get("resp_bpm", 0.0) or 0.0), 1),
            "heart_bpm": round(float(telemetry.get("heart_bpm", 0.0) or 0.0), 1),
            "available": bool(telemetry.get("resp_bpm") or telemetry.get("heart_bpm")),
        },
        "motion": {
            "display_level": str(motion.get("display_level") or "UNKNOWN"),
            "score": round(float(motion.get("score", 0.0) or 0.0), 3),
            "state": str(cadence.get("state") or "unknown"),
            "cadence_spm": round(float(cadence.get("cadence_spm", 0.0) or 0.0), 1),
            "trusted": bool(cadence.get("trusted") or motion.get("trusted")),
            "trust_reason": str(cadence.get("trust_reason") or "not_available"),
        },
        "fingerprint": snapshot.get("fingerprint") or {},
        "spectrogram": snapshot.get("spectrogram") or {},
        "room_state": snapshot.get("room_state") or {},
        "material_change": snapshot.get("material_change") or {},
        "config": config or {},
        "snapshot": snapshot,
    }


def _visual_projection(
    telemetry: dict[str, Any],
    quality: dict[str, Any],
    occupancy: dict[str, Any],
    motion: dict[str, Any],
    cadence: dict[str, Any],
) -> dict[str, Any]:
    quality_status = str(quality.get("status") or "UNKNOWN")
    occupancy_class = str(occupancy.get("class") or "UNKNOWN")
    occupancy_trusted = bool(occupancy.get("trusted"))
    presence = bool(telemetry.get("presence")) or occupancy_class == "OCCUPIED"
    fall_detected = bool(telemetry.get("fall_detected") or telemetry.get("fall_alert"))
    reasons = list(quality.get("reasons") or [])
    reasons.extend(str(reason) for reason in occupancy.get("reasons") or [])

    if quality_status != "GOOD":
        return _visual_result(
            "unknown",
            "transparent",
            "weak",
            0.28,
            ["signal_quality_not_good", *reasons],
        )

    if occupancy_class == "EMPTY" and occupancy_trusted:
        return _visual_result("none", "none", "trusted", 0.0, ["trusted_empty_room"])

    if not presence or not occupancy_trusted:
        return _visual_result(
            "unknown",
            "transparent",
            "blocked",
            0.2,
            ["occupancy_not_trusted", *reasons],
        )

    if fall_detected:
        return _visual_result(
            "fallen", "fallen", "trusted", 0.9, ["fall_event_detected"]
        )

    cadence_state = str(cadence.get("state") or "")
    if cadence_state in {"walking", "running"} and cadence.get("trusted"):
        return _visual_result(
            "walking", "walking", "trusted", 0.92, ["trusted_motion_cadence"]
        )

    if int(telemetry.get("rep_count", 0) or 0) > 0:
        return _visual_result(
            "exercise", "exercise", "trusted", 0.9, ["repetition_motion_detected"]
        )

    motion_level = str(motion.get("display_level") or "UNKNOWN")
    if motion_level in {"MODERATE", "HIGH"}:
        return _visual_result(
            "moving", "walking", "trusted", 0.84, ["motion_energy_detected"]
        )

    return _visual_result(
        "sitting", "sitting", "trusted", 0.86, ["trusted_occupied_still"]
    )


def _visual_result(
    pose_state: str, avatar: str, trust: str, opacity: float, reasons: list[str]
) -> dict[str, Any]:
    deduped_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    return {
        "pose_state": pose_state,
        "avatar": avatar,
        "trust": trust,
        "opacity": opacity,
        "claim": CLAIM,
        "reasons": deduped_reasons,
    }


def _unknown_person_count() -> dict[str, Any]:
    return {
        "estimate": 0,
        "range": "unknown",
        "label": "count unavailable",
        "confidence": "low",
        "trusted": False,
        "reasons": ["person_count_not_available"],
    }
