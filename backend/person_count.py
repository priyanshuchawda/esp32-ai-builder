"""Conservative person-count estimate for a single ESP32 CSI link."""

from __future__ import annotations


def estimate_person_count(snapshot: dict) -> dict:
    quality = snapshot.get("quality") or {}
    telemetry = snapshot.get("telemetry") or {}
    occupancy = telemetry.get("occupancy") or {}
    motion = telemetry.get("motion") or {}
    fingerprint = snapshot.get("fingerprint") or {}
    cadence = snapshot.get("motion_cadence") or {}

    quality_status = quality.get("status")
    occupancy_class = occupancy.get("class", "UNKNOWN")
    occupancy_trusted = bool(occupancy.get("trusted"))
    spread = float(fingerprint.get("spread", 0.0) or 0.0)
    motion_level = motion.get("display_level", motion.get("level", "STILL"))

    if quality_status != "GOOD":
        return _result(0, "unknown", "count blocked", "low", False, ["signal_quality_not_good"])

    if occupancy_class == "EMPTY" and occupancy_trusted:
        return _result(0, "0", "empty room", "high", True, ["trusted_empty_baseline"])

    if occupancy_class != "OCCUPIED" or not occupancy_trusted:
        return _result(0, "unknown", "count blocked", "low", False, ["occupancy_not_trusted"])

    reasons = ["single_link_estimate"]
    moving = motion_level in {"MODERATE", "HIGH"} or cadence.get("state") in {"walking", "running"}
    if spread >= 30.0 and moving:
        return _result(2, "2+", "multi-zone candidate", "low", True, reasons + ["high_spread_motion"])

    confidence = "high" if spread < 18.0 and motion_level in {"STILL", "LOW"} else "medium"
    return _result(1, "1", "single occupied zone", confidence, True, reasons)


def _result(estimate: int, count_range: str, label: str, confidence: str, trusted: bool, reasons: list[str]) -> dict:
    return {
        "estimate": estimate,
        "range": count_range,
        "label": label,
        "confidence": confidence,
        "trusted": trusted,
        "reasons": reasons,
    }
