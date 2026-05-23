def build_signal_recommendations(signal_quality, confidence, telemetry, limit=4):
    signal_quality = signal_quality or {}
    confidence = confidence or {}
    telemetry = telemetry or {}
    reasons = set(signal_quality.get("reasons", [])) | set(confidence.get("reasons", []))
    calibration = telemetry.get("calibration", {}) or {}
    recommendations = []

    def add(code, title, action):
        if code not in [item["code"] for item in recommendations]:
            recommendations.append({"code": code, "title": title, "action": action})

    if signal_quality.get("status") == "GOOD" and confidence.get("alert_allowed") and calibration.get("ready"):
        return [
            {
                "code": "ready",
                "title": "Ready for confident detection",
                "action": "Keep ESP32 and router positions fixed while collecting activity samples.",
            }
        ]

    if "no_packets" in reasons or "stale_stream" in reasons:
        add(
            "restore_udp_stream",
            "Restore CSI packet stream",
            "Check ESP32 power, COM5 serial logs, Wi-Fi connection, and that UDP port 5005 reaches this laptop.",
        )

    if not calibration.get("ready") or "calibration_not_ready" in reasons:
        add(
            "calibrate_empty_room",
            "Run empty-room calibration",
            "Leave the room empty, click Calibrate Empty, and wait for the calibration state to become READY.",
        )

    if "very_low_fps" in reasons or "low_fps" in reasons:
        fps = signal_quality.get("fps", 0.0)
        add(
            "improve_packet_rate",
            "Improve CSI packet rate",
            f"Current rate is about {fps:.1f} FPS; keep ESP32 near the router/laptop and reduce other Wi-Fi traffic.",
        )

    if "rssi_unstable" in reasons:
        add(
            "stabilize_rssi",
            "Stabilize RSSI",
            "Keep ESP32, router, and laptop stationary; avoid touching the USB cable during a capture.",
        )

    if "mixed_subcarriers" in reasons:
        add(
            "stabilize_csi_mode",
            "Stabilize CSI frame mode",
            "Use one fixed 2.4 GHz access point/channel and avoid roaming or reconnecting during a session.",
        )

    if not recommendations:
        add(
            "collect_more_data",
            "Collect more live samples",
            "Keep the setup fixed for 30-60 seconds so quality and confidence can settle.",
        )

    return recommendations[: int(limit)]
