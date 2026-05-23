from fastapi.testclient import TestClient

from backend.main import app


def test_judge_live_api_wraps_actual_probe_payload(monkeypatch):
    calls = {}

    def fake_run_udp_probe(bind_ip, udp_port, duration_sec, min_fps):
        calls.update(
            {
                "bind_ip": bind_ip,
                "udp_port": udp_port,
                "duration_sec": duration_sec,
                "min_fps": min_fps,
            }
        )
        return (
            {"status": "PASS", "reason": "ok", "packets": 42, "fps": 14.0},
            {"status": "GOOD", "fps": 14.0, "reasons": []},
            {128: 42},
            {"class": "OCCUPIED", "trusted": True, "reasons": []},
            {"bins": 16, "mean": 21.5, "spread": 8.0, "bars": "..::==++**##--__"},
            {"source": "live_udp_frames", "time_bins": 3, "subcarrier_bins": 4, "rows": [[0, 20, 60, 100]], "ascii": ".-*#"},
        )

    monkeypatch.setattr("backend.main.run_udp_probe", fake_run_udp_probe)
    monkeypatch.setattr(
        "backend.main.load_firmware_network_config",
        lambda path: {"target_ip": "192.168.29.10", "target_port": 5005},
    )
    monkeypatch.setattr("backend.main.detect_local_ip", lambda: "192.168.29.10")

    client = TestClient(app)
    response = client.get("/api/judge-live?duration=2&bind_ip=0.0.0.0&udp_port=5005&min_fps=4.5")

    assert response.status_code == 200
    data = response.json()
    assert calls == {"bind_ip": "0.0.0.0", "udp_port": 5005, "duration_sec": 2, "min_fps": 4.5}
    assert data["source"] == "actual_udp_probe"
    assert data["overall_status"] == "PASS"
    assert data["udp"]["packets"] == 42
    assert data["config"]["target_ip"] == "192.168.29.10"
    assert data["snapshot"]["source"] == "actual_udp_probe"
    assert data["snapshot"]["quality"]["fps"] == 14.0
    assert data["snapshot"]["summary"]["demo_state"] == "OCCUPIED_STILL"
    assert data["snapshot"]["room_state"]["label"]
    assert data["snapshot"]["fingerprint"]["bars"].isascii()
    assert data["snapshot"]["spectrogram"]["source"] == "live_udp_frames"
