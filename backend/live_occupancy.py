def classify_occupancy(telemetry, signal_quality, evaluator_report):
    telemetry = telemetry or {}
    signal_quality = signal_quality or {}
    evaluator_report = evaluator_report or {}
    readiness = evaluator_report.get("readiness", {})
    model = evaluator_report.get("model", {})

    reasons = []
    quality_status = str(signal_quality.get("status", "BAD")).upper()
    quality_usable = _quality_supports_occupancy(quality_status, signal_quality.get("reasons", []))
    if quality_status == "BAD":
        reasons.append("signal_quality_bad")

    if not readiness.get("ready", False):
        reasons.append("evaluator_not_ready")

    feature = model.get("feature", "filtered_variance")
    threshold = float(model.get("threshold", 0.0) or 0.0)
    value = _feature_value(telemetry, feature)

    would_be_occupied = value > threshold
    if not quality_usable and quality_status == "WEAK":
        if would_be_occupied:
            reasons.append("signal_quality_weak_blocked")
        else:
            reasons.append("weak_signal_cannot_confirm_empty")

    if reasons:
        occupancy_class = "UNKNOWN"
        trusted = False
    elif would_be_occupied:
        occupancy_class = "OCCUPIED"
        trusted = True
    else:
        occupancy_class = "EMPTY"
        trusted = True

    return {
        "class": occupancy_class,
        "trusted": trusted,
        "feature": feature,
        "value": round(value, 4),
        "threshold": round(threshold, 4),
        "reasons": reasons,
    }


def _feature_value(telemetry, feature):
    if feature == "filtered_variance":
        return float(telemetry.get("variance", 0.0) or 0.0)
    return float(telemetry.get(feature, 0.0) or 0.0)


def _quality_supports_occupancy(quality_status, quality_reasons):
    if quality_status == "GOOD":
        return True
    if quality_status != "WEAK":
        return False

    tolerated_reasons = {"rssi_outliers"}
    return set(quality_reasons or []).issubset(tolerated_reasons)
