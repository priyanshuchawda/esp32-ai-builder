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


def test_firmware_prints_wifi_failure_reason_codes():
    source = Path("src/main.cpp").read_text(encoding="utf-8")

    required_markers = [
        "onWifiEvent",
        "WiFi.onEvent",
        "g_lastWifiDisconnectReason",
        "beginConfiguredWifi",
        "WIFI_CHANNEL",
        "WIFI_BSSID",
        "WIFI_STATUS_CODE",
        "WIFI_DISCONNECT_REASON",
        "WiFi.setSleep(false)",
        "WiFi.persistent(false)",
    ]

    for marker in required_markers:
        assert marker in source


def test_firmware_has_configurable_csi_filter_mode():
    source = Path("src/main.cpp").read_text(encoding="utf-8")
    example = Path("include/wifi_credentials.example.h").read_text(encoding="utf-8")

    assert "CSI_PROMISCUOUS_FILTER_MASK" in source
    assert ".filter_mask = CSI_PROMISCUOUS_FILTER_MASK" in source
    assert "WIFI_PROMIS_FILTER_MASK_DATA" in example
