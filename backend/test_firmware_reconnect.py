from pathlib import Path


def test_firmware_has_reconnect_and_csi_reenable_hooks():
    source = Path("src/main.cpp").read_text(encoding="utf-8")

    required_markers = [
        "kReconnectIntervalMs",
        "kStatusPrintIntervalMs",
        "connectWifiWithTimeout",
        "configureRealCsiCapture",
        "ensureWifiConnected",
        "WIFI_DISCONNECTED_RECONNECTING",
        "REAL_CSI_REENABLE_ATTEMPT",
    ]

    for marker in required_markers:
        assert marker in source
