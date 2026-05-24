import json

from fastapi.testclient import TestClient

from backend.main import app


def _write_label_records(directory, label, base_value, count=3):
    path = directory / f"{label}.jsonl"
    records = []
    for index in range(count):
        records.append(
            {
                "label": label,
                "session_id": f"{label}-{index}",
                "window_index": index,
                "features": {
                    "rssi_mean": -50 + base_value,
                    "rssi_std": 1,
                    "signal_mean": base_value,
                    "signal_std": 1,
                    "signal_variance": base_value,
                    "signal_energy": base_value,
                    "outlier_ratio": 0,
                    "min_value": base_value,
                    "max_value": base_value + 1,
                    "sample_count": 20,
                    "missing_or_invalid_count": 0,
                },
            }
        )
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_build_calibration_snapshot_reuses_activity_report(tmp_path):
    from backend.calibration_coach import build_calibration_snapshot

    _write_label_records(tmp_path, "empty", 1)
    _write_label_records(tmp_path, "sitting", 10)
    _write_label_records(tmp_path, "walking", 20)

    report = build_calibration_snapshot(tmp_path)

    assert report["readiness"]["ready"] is True
    assert report["readiness"]["labels"]["sitting"]["records"] == 3
    assert report["evaluation"]["eligible"] is True
    assert report["evaluation"]["accuracy"] == 1.0
    assert "labels_dir" not in report


def test_rule_based_coach_selects_missing_label():
    from backend.calibration_coach import build_rule_based_coach_advice

    report = {
        "summary": {"total_records": 6},
        "readiness": {
            "ready": False,
            "labels": {
                "empty": {"records": 0, "needed": 3, "ready": False},
                "sitting": {"records": 3, "needed": 0, "ready": True},
                "walking": {"records": 3, "needed": 0, "ready": True},
            },
            "next_labels": ["empty"],
        },
        "evaluation": {"eligible": True, "accuracy": 0.5},
    }

    advice = build_rule_based_coach_advice(report)

    assert advice["provider"] == "rules"
    assert advice["status"] == "collect"
    assert advice["next_label"] == "empty"
    assert "empty" in advice["next_action"].lower()


def test_calibration_coach_retries_fallback_gemma_model(monkeypatch):
    from backend.calibration_coach import query_calibration_coach

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
                text = '{"status":"collect","headline":"Collect an empty baseline.","evidence":["empty has 0 usable windows"],"next_label":"empty","next_action":"Record empty for 30 seconds.","judge_caption":"Calibration requires an empty-room baseline."}'

            return Response()

    class FakeClient:
        models = FakeModels()

    advice = query_calibration_coach(
        {"readiness": {"ready": False, "next_labels": ["empty"]}},
        client_factory=lambda: FakeClient(),
    )

    assert calls == ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
    assert advice["provider"] == "gemini"
    assert advice["model"] == "gemma-4-26b-a4b-it"
    assert advice["fallback_used"] is True


def test_calibration_coach_endpoint_returns_compact_advice(monkeypatch):
    compact = {
        "summary": {"total_records": 9},
        "readiness": {"ready": True, "labels": {}, "next_labels": []},
        "evaluation": {"eligible": True, "accuracy": 1.0},
    }
    monkeypatch.setattr("backend.main.build_calibration_snapshot", lambda: compact)
    monkeypatch.setattr(
        "backend.main.query_calibration_coach",
        lambda _report: {"provider": "rules", "status": "ready", "next_label": "none"},
    )

    response = TestClient(app).get("/api/calibration-coach")

    assert response.status_code == 200
    assert response.json()["report"] == compact
    assert response.json()["advice"]["status"] == "ready"
