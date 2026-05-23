from fastapi.testclient import TestClient

from backend.main import app


def test_judge_demo_payload_contains_scenarios_and_live_snapshot():
    client = TestClient(app)

    response = client.get("/api/judge-demo")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "ESP32 Wi-Fi CSI Spatial Intelligence"
    assert len(data["scenarios"]) >= 5
    assert data["live"]["summary"]["demo_state"]
    assert data["live"]["room_state"]["label"]
    assert data["scenarios"][0]["fingerprint"]["bars"].isascii()
    assert data["scenarios"][0]["room_state"]["cluster_id"] >= 0
    assert data["pipeline"][0]["label"] == "ESP32 DevKit V1"


def test_judge_demo_payload_can_select_scenario():
    client = TestClient(app)

    response = client.get("/api/judge-demo?scenario=walking")

    assert response.status_code == 200
    data = response.json()
    assert data["selected"]["scenario"] == "walking"
    assert data["selected"]["summary"]["demo_state"] == "OCCUPIED_MOVING"
