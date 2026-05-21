from unittest.mock import patch, MagicMock
import requests
from gemma_advisor import (
    cleanse_json_response,
    config,
    get_rule_based_decision,
    query_gemma_advisor,
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


@patch("requests.post")
def test_query_gemma_advisor_success(mock_post):
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
    decision = query_gemma_advisor(features)

    assert decision["filter"] == "hampel"
    assert decision["window_size"] == 9
    assert decision["outlier_threshold"] == 2.5
    assert decision["confidence"] == 0.95
    assert mock_post.call_args.kwargs["timeout"] == config.OLLAMA_TIMEOUT_SECONDS


@patch("requests.post")
def test_query_gemma_advisor_failure_fallback(mock_post):
    # Mock connection timeout/failure
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

    features = {"outlier_ratio": 0.20, "signal_std": 1.2}
    # Should fall back to rule-based because requests raised an error
    decision = query_gemma_advisor(features)

    assert decision is not None
    # Features has outlier_ratio > 0.10, so fallback should recommend median
    assert decision["filter"] == "median"
    assert "Rule-based fallback" in decision["reason"]
