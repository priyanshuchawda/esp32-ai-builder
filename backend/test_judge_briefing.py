from fastapi.testclient import TestClient

from backend.main import app


WEAK_OBSERVATORY = {
    "source": "actual_udp_probe",
    "truth_label": "visualization_only_not_densepose",
    "visual": {
        "pose_state": "unknown",
        "trust": "weak",
        "reasons": ["signal_quality_not_good"],
    },
    "persons": {"range": "unknown", "trusted": False},
    "signal": {"quality": "WEAK", "fps": 2.0, "packets": 7, "reasons": ["low_fps"]},
    "vitals": {"available": False, "trusted": False},
    "motion": {"state": "insufficient_data", "display_level": "UNSTABLE"},
}

CALIBRATION = {
    "summary": {"total_records": 31},
    "readiness": {"ready": False, "next_labels": ["empty"]},
    "evaluation": {"eligible": True, "accuracy": 0.5},
}


def test_rule_briefing_preserves_weak_signal_gate():
    from backend.judge_briefing import build_rule_based_briefing

    briefing = build_rule_based_briefing(WEAK_OBSERVATORY, CALIBRATION)

    assert briefing["provider"] == "rules"
    assert "no trusted activity" in briefing["sensing_claim"].lower()
    assert "wi-fi csi" in " ".join(briefing["limitations"]).lower()
    assert "empty" in briefing["calibration_context"].lower()


def test_judge_briefing_retries_fallback_gemma_model(monkeypatch):
    from backend.judge_briefing import query_judge_briefing

    monkeypatch.setattr("backend.ai_advice.GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("backend.ai_advice.GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(
        "backend.ai_advice.GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it"
    )
    calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs["model"])
            if kwargs["model"] == "gemma-4-31b-it":
                raise RuntimeError("primary unavailable")

            class Response:
                text = '{"title":"CSI evidence briefing","sensing_claim":"Walking detected.","evidence":["motion seen"],"calibration_context":"ready","limitations":["none"],"next_action":"continue"}'

            return Response()

    class FakeClient:
        models = FakeModels()

    briefing = query_judge_briefing(
        WEAK_OBSERVATORY, CALIBRATION, client_factory=lambda: FakeClient()
    )

    assert calls == ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
    assert briefing["provider"] == "gemini"
    assert briefing["fallback_used"] is True
    assert "no trusted activity" in briefing["sensing_claim"].lower()


def test_judge_briefing_endpoint_uses_posted_snapshot_without_probe(monkeypatch):
    def fail_if_probed(**_kwargs):
        raise AssertionError("briefing must not run a live probe")

    monkeypatch.setattr("backend.main.run_udp_probe", fail_if_probed)
    monkeypatch.setattr("backend.main.build_calibration_snapshot", lambda: CALIBRATION)
    monkeypatch.setattr(
        "backend.main.query_judge_briefing",
        lambda _observatory, _calibration: {
            "provider": "rules",
            "title": "Briefing",
            "sensing_claim": "No trusted claim.",
        },
    )

    response = TestClient(app).post(
        "/api/judge-briefing", json={"observatory": WEAK_OBSERVATORY}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["event_signature"] == "actual_udp_probe|WEAK|weak|unknown|unknown|insufficient_data"
    assert data["calibration"]["readiness"]["next_labels"] == ["empty"]
