from unittest.mock import patch, MagicMock
import requests
from gemma_advisor import (
    cleanse_json_response,
    config,
    get_rule_based_decision,
    query_gemini_advisor,
    query_gemma_advisor,
    query_ollama_advisor,
)


def test_cleanse_json_response():
    # Test with standard markdown wrap
    text_with_markdown = '```json\n{\n  "filter": "median"\n}\n```'
    cleansed = cleanse_json_response(text_with_markdown)
    assert cleansed == '{\n  "filter": "median"\n}'

    # Test with generic codeblock wrap
    text_generic = '```\n{\n  "filter": "moving_average"\n}\n```'
    cleansed_generic = cleanse_json_response(text_generic)
    assert cleansed_generic == '{\n  "filter": "moving_average"\n}'

    # Test with normal text
    normal = '{"filter": "lowpass"}'
    assert cleanse_json_response(normal) == normal


def test_get_rule_based_decision():
    # 1. Outlier ratio > 0.10 -> median
    features_outlier = {"outlier_ratio": 0.15, "signal_std": 0.5}
    decision = get_rule_based_decision(features_outlier)
    assert decision["filter"] == "median"
    assert decision["window_size"] == 5

    # 2. signal_std > 2.0 -> moving_average
    features_high_std = {"outlier_ratio": 0.05, "signal_std": 2.5}
    decision_std = get_rule_based_decision(features_high_std)
    assert decision_std["filter"] == "moving_average"
    assert decision_std["window_size"] == 7

    # 3. signal_std > 0.2 -> lowpass
    features_noise = {"outlier_ratio": 0.02, "signal_std": 0.8}
    decision_noise = get_rule_based_decision(features_noise)
    assert decision_noise["filter"] == "lowpass"
    assert decision_noise["lowpass_alpha"] == 0.25

    # 4. quiet -> none
    features_quiet = {"outlier_ratio": 0.0, "signal_std": 0.1}
    decision_quiet = get_rule_based_decision(features_quiet)
    assert decision_quiet["filter"] == "none"


def test_query_gemini_advisor_success(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(config, "GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it")

    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '```json\n{\n  "filter": "hampel",\n  "window_size": 9,\n  "outlier_threshold": 2.5,\n  "lowpass_alpha": 0.25,\n  "confidence": 0.95,\n  "reason": "High variance with spike noise"\n}\n```'
    fake_client.models.generate_content.return_value = fake_response

    features = {"outlier_ratio": 0.05, "signal_std": 1.2}
    decision = query_gemini_advisor(features, client_factory=lambda: fake_client)

    assert decision["filter"] == "hampel"
    assert decision["window_size"] == 9
    assert decision["outlier_threshold"] == 2.5
    assert decision["confidence"] == 0.95
    assert decision["advisor_provider"] == "gemini"
    assert decision["advisor_model"] == "gemma-4-31b-it"
    assert decision["advisor_fallback_used"] is False

    call = fake_client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemma-4-31b-it"
    assert "summary features" in call.kwargs["contents"]
    assert call.kwargs["config"].response_mime_type == "application/json"


def test_query_gemini_advisor_uses_fallback_model_after_primary_error(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(config, "GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it")

    fake_client = MagicMock()
    fallback_response = MagicMock()
    fallback_response.text = '{\n  "filter": "lowpass",\n  "window_size": 5,\n  "outlier_threshold": 3.0,\n  "lowpass_alpha": 0.18,\n  "confidence": 0.87,\n  "reason": "Fallback model selected smoother lowpass filtering."\n}'
    fake_client.models.generate_content.side_effect = [
        RuntimeError("primary unavailable"),
        fallback_response,
    ]

    features = {"outlier_ratio": 0.02, "signal_std": 0.7}
    decision = query_gemini_advisor(features, client_factory=lambda: fake_client)

    assert decision["filter"] == "lowpass"
    assert decision["lowpass_alpha"] == 0.18
    assert decision["advisor_provider"] == "gemini"
    assert decision["advisor_model"] == "gemma-4-26b-a4b-it"
    assert decision["advisor_primary_model"] == "gemma-4-31b-it"
    assert decision["advisor_fallback_used"] is True

    calls = fake_client.models.generate_content.call_args_list
    assert [call.kwargs["model"] for call in calls] == [
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    ]


def test_query_gemini_advisor_builds_client_with_bounded_timeout(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_HTTP_TIMEOUT_MS", 12345)

    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"filter":"none","window_size":3,"outlier_threshold":3.0,"lowpass_alpha":0.25,"confidence":0.8,"reason":"Quiet signal."}'
    fake_client.models.generate_content.return_value = fake_response
    captured = {}

    def fake_client_factory(**kwargs):
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr("gemma_advisor.genai.Client", fake_client_factory)

    query_gemini_advisor({"outlier_ratio": 0.0, "signal_std": 0.1})

    assert captured["http_options"].timeout == 12345


def test_query_gemini_advisor_avoids_duplicate_fallback_model(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_GEMMA_MODEL", "gemma-4-31b-it")
    monkeypatch.setattr(config, "GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-31b-it")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = RuntimeError("model unavailable")

    features = {"outlier_ratio": 0.20, "signal_std": 1.2}
    decision = query_gemini_advisor(features, client_factory=lambda: fake_client)

    assert fake_client.models.generate_content.call_count == 1
    assert decision["filter"] == "median"
    assert decision["advisor_provider"] == "rules"
    assert decision["advisor_model"] == "rules"


def test_query_gemma_advisor_falls_back_without_gemini_key(monkeypatch):
    monkeypatch.setattr(config, "GEMMA_ADVISOR_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    features = {"outlier_ratio": 0.20, "signal_std": 1.2}
    decision = query_gemma_advisor(features)

    assert decision["filter"] == "median"
    assert "Rule-based fallback" in decision["reason"]


def test_query_gemma_advisor_supports_rules_provider(monkeypatch):
    monkeypatch.setattr(config, "GEMMA_ADVISOR_PROVIDER", "rules")

    features = {"outlier_ratio": 0.0, "signal_std": 2.5}
    decision = query_gemma_advisor(features)

    assert decision["filter"] == "moving_average"
    assert "Rule-based fallback" in decision["reason"]


@patch("requests.post")
def test_query_ollama_advisor_success(mock_post):
    # Mock a successful response from Ollama API
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "content": '```json\n{\n  "filter": "hampel",\n  "window_size": 9,\n  "outlier_threshold": 2.5,\n  "lowpass_alpha": 0.25,\n  "confidence": 0.95,\n  "reason": "High variance with spike noise"\n}\n```'
        }
    }
    mock_post.return_value = mock_resp

    features = {"outlier_ratio": 0.05, "signal_std": 1.2}
    decision = query_ollama_advisor(features)

    assert decision["filter"] == "hampel"
    assert decision["window_size"] == 9
    assert decision["outlier_threshold"] == 2.5
    assert decision["confidence"] == 0.95
    assert mock_post.call_args.kwargs["timeout"] == config.OLLAMA_TIMEOUT_SECONDS


@patch("requests.post")
def test_query_ollama_advisor_failure_fallback(mock_post):
    # Mock connection timeout/failure
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

    features = {"outlier_ratio": 0.20, "signal_std": 1.2}
    # Should fall back to rule-based because requests raised an error
    decision = query_ollama_advisor(features)

    assert decision is not None
    # Features has outlier_ratio > 0.10, so fallback should recommend median
    assert decision["filter"] == "median"
    assert "Rule-based fallback" in decision["reason"]
