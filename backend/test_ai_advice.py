from fastapi.testclient import TestClient

from backend.main import app


WEAK_OBSERVATORY = {
    "source": "actual_udp_probe",
    "truth_label": "visualization_only_not_densepose",
    "visual": {
        "pose_state": "unknown",
        "avatar": "transparent",
        "trust": "weak",
        "opacity": 0.28,
        "claim": "CSI-inferred activity visualization",
        "reasons": ["signal_quality_not_good", "low_fps"],
    },
    "persons": {"range": "unknown", "label": "count blocked", "trusted": False},
    "signal": {"quality": "WEAK", "fps": 1.8, "packets": 9, "reasons": ["low_fps"]},
    "vitals": {"resp_bpm": 0.0, "heart_bpm": 0.0, "available": False},
    "motion": {
        "display_level": "UNSTABLE",
        "state": "insufficient_data",
        "cadence_spm": 0.0,
        "trusted": False,
    },
}


def test_rule_based_ai_advice_blocks_weak_signal(monkeypatch):
    monkeypatch.setattr("backend.ai_advice.GEMINI_API_KEY", "")

    from backend.ai_advice import query_ai_advice

    advice = query_ai_advice(WEAK_OBSERVATORY)

    assert advice["provider"] == "rules"
    assert advice["model"] == "rules"
    assert advice["status"] == "weak"
    assert "low fps" in " ".join(advice["why"]).lower()
    assert advice["next_action"]
    assert advice["telegram_message"]


def test_ai_advice_uses_primary_gemma_model(monkeypatch):
    monkeypatch.setattr("backend.ai_advice.GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("backend.ai_advice.GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(
        "backend.ai_advice.GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it"
    )

    class FakeModels:
        calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs)

            class Response:
                text = '{"status":"trusted","room_interpretation":"Walking rhythm is visible.","why":["quality is good"],"next_action":"Keep the ESP position stable.","judge_caption":"Gemma explains trusted RF motion.","telegram_message":"Trusted walking candidate.","confidence":0.91}'

            return Response()

    fake_models = FakeModels()

    class FakeClient:
        models = fake_models

    from backend.ai_advice import query_ai_advice

    advice = query_ai_advice(WEAK_OBSERVATORY, client_factory=lambda: FakeClient())

    assert advice["provider"] == "gemini"
    assert advice["model"] == "gemma-4-31b-it"
    assert advice["fallback_used"] is False
    assert advice["status"] == "weak"
    assert "blocked" in advice["judge_caption"].lower()
    assert "trusted walking" not in advice["telegram_message"].lower()
    assert fake_models.calls[0]["model"] == "gemma-4-31b-it"


def test_ai_advice_retries_fallback_gemma_model(monkeypatch):
    monkeypatch.setattr("backend.ai_advice.GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("backend.ai_advice.GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(
        "backend.ai_advice.GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it"
    )

    class FakeModels:
        calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["model"] == "gemma-4-31b-it":
                raise RuntimeError("primary unavailable")

            class Response:
                text = '{"status":"weak","room_interpretation":"Signal is visible but weak.","why":["fallback model used"],"next_action":"Improve packet rate.","judge_caption":"Gemma fallback explains weak RF.","telegram_message":"Signal weak; no trusted person count.","confidence":0.78}'

            return Response()

    fake_models = FakeModels()

    class FakeClient:
        models = fake_models

    from backend.ai_advice import query_ai_advice

    advice = query_ai_advice(WEAK_OBSERVATORY, client_factory=lambda: FakeClient())

    assert advice["provider"] == "gemini"
    assert advice["model"] == "gemma-4-26b-a4b-it"
    assert advice["primary_model"] == "gemma-4-31b-it"
    assert advice["fallback_used"] is True
    assert [call["model"] for call in fake_models.calls] == [
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    ]


def test_ai_advice_builds_hosted_client_with_bounded_timeout(monkeypatch):
    monkeypatch.setattr("backend.ai_advice.GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("backend.ai_advice.GEMINI_HTTP_TIMEOUT_MS", 12345)
    captured = {}

    class FakeModels:
        def generate_content(self, **_kwargs):
            class Response:
                text = '{"status":"weak","room_interpretation":"Signal weak.","why":["weak"],"next_action":"Wait.","judge_caption":"Blocked.","telegram_message":"Weak CSI.","confidence":0.4}'

            return Response()

    class FakeClient:
        models = FakeModels()

    def fake_client(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr("backend.ai_advice.genai.Client", fake_client)

    from backend.ai_advice import query_ai_advice

    query_ai_advice(WEAK_OBSERVATORY)

    assert captured["http_options"].timeout == 12345


def test_ai_advice_aligns_empty_room_trust_gate(monkeypatch):
    monkeypatch.setattr("backend.ai_advice.GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("backend.ai_advice.GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(
        "backend.ai_advice.GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it"
    )

    trusted_empty = {
        **WEAK_OBSERVATORY,
        "visual": {
            **WEAK_OBSERVATORY["visual"],
            "pose_state": "none",
            "trust": "trusted",
            "reasons": ["empty_room_baseline"],
        },
        "persons": {"range": "0", "label": "empty baseline", "trusted": True},
        "signal": {
            **WEAK_OBSERVATORY["signal"],
            "quality": "GOOD",
            "fps": 34.0,
            "packets": 102,
            "reasons": [],
        },
    }

    class FakeModels:
        def generate_content(self, **_kwargs):
            class Response:
                text = '{"status":"weak","room_interpretation":"No moving person is visible.","why":["no motion"],"next_action":"Collect more packets.","judge_caption":"Gemma says weak.","telegram_message":"Weak CSI.","confidence":0.62}'

            return Response()

    class FakeClient:
        models = FakeModels()

    from backend.ai_advice import query_ai_advice

    advice = query_ai_advice(trusted_empty, client_factory=lambda: FakeClient())

    assert advice["provider"] == "gemini"
    assert advice["status"] == "trusted"
    assert "empty-room baseline" in advice["room_interpretation"]
    assert advice["confidence"] >= 0.8


def test_ai_advice_api_returns_demo_advice(monkeypatch):
    monkeypatch.setattr(
        "backend.main.query_ai_advice",
        lambda observatory: {
            "provider": "rules",
            "model": "rules",
            "primary_model": "rules",
            "fallback_used": False,
            "status": "trusted",
            "room_interpretation": "Demo room state is explainable.",
            "why": ["demo"],
            "next_action": "Show Observatory.",
            "judge_caption": "Gemma-ready RF explanation.",
            "telegram_message": "Demo trusted.",
            "confidence": 1.0,
        },
    )

    client = TestClient(app)
    response = client.get("/api/ai-advice?mode=demo&scenario=walking")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "demo"
    assert data["advice"]["judge_caption"] == "Gemma-ready RF explanation."
    assert data["observatory"]["visual"]["pose_state"] == "walking"
