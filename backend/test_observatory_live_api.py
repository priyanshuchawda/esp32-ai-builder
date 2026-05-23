from fastapi.testclient import TestClient

from backend.main import app


def test_observatory_demo_projects_walking_avatar():
    client = TestClient(app)

    response = client.get("/api/observatory-live?mode=demo&scenario=walking")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "demo"
    assert data["visual"]["pose_state"] == "walking"
    assert data["visual"]["avatar"] == "walking"
    assert data["visual"]["trust"] == "trusted"
    assert data["visual"]["claim"] == "CSI-inferred activity visualization"
    assert data["persons"]["range"] == "1"
    assert data["signal"]["quality"] == "GOOD"
    assert data["motion"]["state"] == "walking"
    assert data["truth_label"] == "visualization_only_not_densepose"


def test_observatory_demo_blocks_weak_stream_avatar():
    client = TestClient(app)

    response = client.get("/api/observatory-live?mode=demo&scenario=weak_live_stream")

    assert response.status_code == 200
    data = response.json()
    assert data["visual"]["pose_state"] == "unknown"
    assert data["visual"]["avatar"] == "transparent"
    assert data["visual"]["trust"] == "weak"
    assert "signal_quality_not_good" in data["visual"]["reasons"]
    assert data["persons"]["range"] == "unknown"
    assert data["signal"]["quality"] == "WEAK"


def test_observatory_live_uses_probe_snapshot(monkeypatch):
    def fake_run_udp_probe(bind_ip, udp_port, duration_sec, min_fps):
        return (
            {"status": "PASS", "reason": "ok", "packets": 60, "fps": 20.0},
            {"status": "GOOD", "fps": 20.0, "reasons": []},
            {128: 60},
            {"class": "OCCUPIED", "trusted": True, "reasons": []},
            {
                "presence": True,
                "resp_bpm": 18.0,
                "heart_bpm": 88.0,
                "fall_detected": False,
                "variance": 24.5,
                "motion": {"display_level": "HIGH", "score": 4.5, "trusted": True},
            },
            {"bins": 16, "mean": 20.0, "spread": 20.0, "bars": "..::==++**##--__"},
            {
                "source": "live_udp_frames",
                "time_bins": 2,
                "subcarrier_bins": 2,
                "rows": [[0, 100]],
                "ascii": ".#",
            },
            {
                "state": "walking",
                "trusted": True,
                "cadence_spm": 98.0,
                "dominant_frequency_hz": 1.633,
                "regularity": 0.71,
                "stride_regularity": 0.62,
                "sample_count": 120,
                "trust_reason": "quality_good",
            },
        )

    monkeypatch.setattr("backend.main.run_udp_probe", fake_run_udp_probe)
    monkeypatch.setattr(
        "backend.main.load_firmware_network_config",
        lambda path: {"target_ip": "192.168.29.10", "target_port": 5005},
    )
    monkeypatch.setattr("backend.main.detect_local_ip", lambda: "192.168.29.10")

    client = TestClient(app)
    response = client.get(
        "/api/observatory-live?mode=live&duration=2&udp_port=5005&min_fps=5"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "actual_udp_probe"
    assert data["visual"]["pose_state"] == "walking"
    assert data["visual"]["trust"] == "trusted"
    assert data["persons"]["range"] == "1"
    assert data["signal"]["packets"] == 60
    assert data["vitals"]["resp_bpm"] == 18.0
    assert data["vitals"]["heart_bpm"] == 88.0
