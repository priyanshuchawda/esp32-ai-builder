def build_power_summary(telemetry, signal_quality):
    telemetry = telemetry or {}
    signal_quality = signal_quality or {}
    motion = telemetry.get("motion", {}) or {}
    occupancy = telemetry.get("occupancy", {}) or {}

    quality_status = str(signal_quality.get("status", "BAD")).upper()
    confidence = _confidence(quality_status, occupancy, motion)
    capabilities = _capabilities(telemetry, occupancy, motion)
    demo_state = _demo_state(telemetry, occupancy, motion, quality_status)
    headline = _headline(demo_state, capabilities)
    next_actions = _next_actions(signal_quality)

    return {
        "demo_state": demo_state,
        "headline": headline,
        "confidence": confidence,
        "capabilities": capabilities,
        "next_actions": next_actions,
        "quality": {
            "status": quality_status,
            "fps": round(float(signal_quality.get("fps", 0.0) or 0.0), 2),
            "reasons": list(signal_quality.get("reasons", []) or []),
        },
        "motion": {
            "level": motion.get("display_level", motion.get("level", "STILL")),
            "score": round(float(motion.get("score", 0.0) or 0.0), 3),
            "trusted": bool(motion.get("trusted", True)),
        },
        "occupancy": {
            "class": occupancy.get("class", "UNKNOWN"),
            "trusted": bool(occupancy.get("trusted", False)),
            "reasons": list(occupancy.get("reasons", []) or []),
        },
        "vitals": {
            "resp_bpm": round(float(telemetry.get("resp_bpm", 0.0) or 0.0), 1),
            "heart_bpm": round(float(telemetry.get("heart_bpm", 0.0) or 0.0), 1),
        },
    }


def format_power_summary_lines(summary, prefix="POWER_SUMMARY"):
    capabilities = ",".join(summary.get("capabilities", [])) or "none"
    next_actions = ",".join(summary.get("next_actions", [])) or "none"
    return [
        f"{prefix} state={summary.get('demo_state', 'UNKNOWN')} confidence={summary.get('confidence', 'LOW')}",
        f"{prefix} headline={summary.get('headline', 'CSI demo state unavailable')}",
        f"{prefix} capabilities={capabilities}",
        f"{prefix} next_actions={next_actions}",
    ]


def _confidence(quality_status, occupancy, motion):
    if quality_status == "GOOD" and occupancy.get("trusted", False) and motion.get("trusted", True):
        return "HIGH"
    if quality_status in {"GOOD", "WEAK"}:
        return "MEDIUM" if occupancy.get("trusted", False) else "LOW"
    return "LOW"


def _capabilities(telemetry, occupancy, motion):
    capabilities = []
    if telemetry.get("presence") or occupancy.get("class") == "OCCUPIED":
        capabilities.append("presence")
    if float(telemetry.get("resp_bpm", 0.0) or 0.0) > 0:
        capabilities.append("breathing")
    if float(telemetry.get("heart_bpm", 0.0) or 0.0) > 0:
        capabilities.append("heart_rate")
    if telemetry.get("fall_detected"):
        capabilities.append("fall_alert")
    if motion.get("display_level", motion.get("level")) in {"MODERATE", "HIGH"}:
        capabilities.append("motion_intensity")
    return capabilities


def _demo_state(telemetry, occupancy, motion, quality_status):
    if quality_status in {"BAD", "WEAK"} and not occupancy.get("trusted", False):
        return "SIGNAL_WATCH"
    if telemetry.get("fall_detected"):
        return "FALL_EVENT"

    occupancy_class = occupancy.get("class", "UNKNOWN")
    motion_level = motion.get("display_level", motion.get("level", "STILL"))
    if occupancy_class == "OCCUPIED" and motion_level in {"STILL", "LOW"}:
        return "OCCUPIED_STILL"
    if occupancy_class == "OCCUPIED" and motion_level in {"MODERATE", "HIGH"}:
        return "OCCUPIED_MOVING"
    if occupancy_class == "EMPTY":
        return "EMPTY_ROOM"
    return "UNKNOWN_ROOM"


def _headline(demo_state, capabilities):
    if demo_state == "FALL_EVENT":
        return "Fall-like motion spike detected"
    if demo_state == "SIGNAL_WATCH":
        return "ESP32 stream is live but confidence is limited"
    if "breathing" in capabilities or "heart_rate" in capabilities:
        return "Human presence visible through Wi-Fi CSI"
    if demo_state == "OCCUPIED_MOVING":
        return "Body motion is changing the Wi-Fi channel"
    if demo_state == "EMPTY_ROOM":
        return "Room baseline looks empty"
    return "CSI demo state available"


def _next_actions(signal_quality):
    reasons = set(signal_quality.get("reasons", []) or [])
    actions = []
    if "low_fps" in reasons or "very_low_fps" in reasons:
        actions.append("improve_wifi_signal_or_reduce_receiver_load")
    if "rssi_unstable" in reasons:
        actions.append("stabilize_esp_router_position")
    if "no_packets" in reasons:
        actions.append("reset_or_reflash_esp_streaming_firmware")
    return actions
