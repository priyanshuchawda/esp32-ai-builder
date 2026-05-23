def evaluate_presence_confidence(telemetry, signal_quality):
    presence = bool(telemetry.get("presence", False))
    variance = float(telemetry.get("variance", 0.0) or 0.0)
    threshold = float(telemetry.get("effective_presence_threshold", 0.0) or 0.0)
    calibration = telemetry.get("calibration", {}) or {}
    calibration_ready = bool(calibration.get("ready", False))
    quality_status = str((signal_quality or {}).get("status", "BAD")).upper()

    if not presence:
        return {
            "score": 0,
            "level": "LOW",
            "alert_allowed": False,
            "label": "ROOM EMPTY",
            "reasons": ["no_presence_decision"],
        }

    reasons = []
    score = 30

    if threshold > 0:
        margin = max(0.0, (variance / threshold) - 1.0)
        score += min(25, int(margin * 15))
    else:
        reasons.append("missing_threshold")

    if calibration_ready:
        score += 25
    else:
        reasons.append("calibration_not_ready")

    if quality_status == "GOOD":
        score += 20
    else:
        reasons.append("signal_quality_not_good")
        if quality_status == "WEAK":
            score += 5

    score = max(0, min(100, int(score)))
    alert_allowed = score >= 90 and calibration_ready and quality_status == "GOOD"

    if alert_allowed:
        level = "HIGH"
        label = "CONFIRMED HUMAN"
    elif score >= 45:
        level = "MEDIUM"
        label = "UNCONFIRMED MOTION"
    else:
        level = "LOW"
        label = "LOW CONFIDENCE MOTION"

    return {
        "score": score,
        "level": level,
        "alert_allowed": alert_allowed,
        "label": label,
        "reasons": reasons,
    }
