from unittest.mock import Mock

import requests

from presence_alerts import (
    PresenceThresholds,
    TelegramPresenceAlerter,
    TelegramSettings,
    build_presence_message,
    detect_human_presence,
)


def test_detect_human_presence_requires_enough_samples_and_motion():
    quiet_features = {
        "sample_count": 120,
        "signal_variance": 0.04,
        "signal_std": 0.2,
        "rssi_std": 0.1,
    }
    active_features = {
        "sample_count": 120,
        "signal_variance": 2.4,
        "signal_std": 1.55,
        "rssi_std": 1.2,
    }
    short_window = {
        "sample_count": 8,
        "signal_variance": 4.0,
        "signal_std": 2.0,
        "rssi_std": 2.0,
    }

    assert detect_human_presence(quiet_features) is False
    assert detect_human_presence(short_window) is False
    assert detect_human_presence(active_features) is True


def test_detect_human_presence_supports_two_second_serial_window():
    serial_window_features = {
        "sample_count": 19,
        "signal_variance": 50.1527,
        "signal_std": 7.0819,
        "rssi_std": 1.2,
    }
    thresholds = PresenceThresholds(min_samples=15)

    assert detect_human_presence(serial_window_features, thresholds) is True


def test_build_presence_message_summarizes_signal_context():
    message = build_presence_message(
        {"signal_variance": 2.3456, "signal_std": 1.2345, "rssi_std": 0.9876},
        {"filter": "median", "confidence": 0.82},
    )

    assert "Human presence likely detected" in message
    assert "variance=2.3456" in message
    assert "filter=median" in message
    assert "confidence=0.82" in message


def test_telegram_alerter_skips_when_disabled_or_missing_credentials():
    post = Mock()
    settings = TelegramSettings(enabled=False, bot_token="token", chat_id="123")
    alerter = TelegramPresenceAlerter(settings, post=post)

    assert alerter.send_presence_alert({}, {}) is False
    post.assert_not_called()

    settings = TelegramSettings(enabled=True, bot_token="", chat_id="123")
    alerter = TelegramPresenceAlerter(settings, post=post)

    assert alerter.send_presence_alert({}, {}) is False
    post.assert_not_called()


def test_telegram_alerter_posts_message_and_honors_cooldown():
    post = Mock()
    post.return_value.status_code = 200
    post.return_value.raise_for_status.return_value = None
    now = Mock(side_effect=[1000.0, 1005.0, 1031.0])
    settings = TelegramSettings(
        enabled=True,
        bot_token="token",
        chat_id="123",
        cooldown_seconds=30,
    )
    alerter = TelegramPresenceAlerter(settings, post=post, now=now)

    assert alerter.send_presence_alert({"signal_variance": 2.0}, {"filter": "lowpass"})
    assert alerter.send_presence_alert({"signal_variance": 3.0}, {"filter": "median"}) is False
    assert alerter.send_presence_alert({"signal_variance": 4.0}, {"filter": "hampel"})

    assert post.call_count == 2
    first_call = post.call_args_list[0]
    assert first_call.args[0] == "https://api.telegram.org/bottoken/sendMessage"
    assert first_call.kwargs["json"]["chat_id"] == "123"
    assert "Human presence likely detected" in first_call.kwargs["json"]["text"]


def test_telegram_alerter_does_not_log_bot_token_on_failure(caplog):
    response = Mock()
    response.status_code = 403
    response.reason = "Forbidden"
    response.raise_for_status.side_effect = requests.HTTPError(
        "403 Client Error: Forbidden for url: https://api.telegram.org/bottoken/sendMessage"
    )
    post = Mock(return_value=response)
    settings = TelegramSettings(enabled=True, bot_token="secret-token", chat_id="123")
    alerter = TelegramPresenceAlerter(settings, post=post)

    assert alerter.send_presence_alert({"signal_variance": 2.0}, {"filter": "median"}) is False
    assert "secret-token" not in caplog.text
    assert "api.telegram.org/bot" not in caplog.text
