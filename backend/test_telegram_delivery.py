import logging
from unittest.mock import Mock

import httpx
from fastapi.testclient import TestClient

from backend.main import app


def test_delivery_returns_not_configured_without_credentials():
    from backend.telegram_delivery import TelegramDeliverySettings, deliver_prepared_message

    result = deliver_prepared_message(
        "CSI quality watch: signal weak.",
        "sig-1",
        settings=TelegramDeliverySettings(bot_token="", chat_id=""),
    )

    assert result["status"] == "not_configured"
    assert result["message_id"] is None


def test_delivery_returns_ack_and_masks_destination():
    from backend.telegram_delivery import TelegramDeliverySettings, deliver_prepared_message

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True, "result": {"message_id": 84}}
    post = Mock(return_value=response)

    result = deliver_prepared_message(
        "CSI quality watch: signal weak.",
        "sig-2",
        settings=TelegramDeliverySettings(
            bot_token="secret-token",
            chat_id="-987654321",
            timeout_seconds=4.0,
        ),
        post=post,
    )

    assert result == {
        "status": "sent",
        "event_signature": "sig-2",
        "message_id": 84,
        "destination": "...4321",
        "detail": "Telegram accepted the prepared message.",
    }
    assert post.call_args.args[0] == "https://api.telegram.org/botsecret-token/sendMessage"
    assert post.call_args.kwargs["json"]["chat_id"] == "-987654321"
    assert post.call_args.kwargs["timeout"] == 4.0


def test_delivery_failure_does_not_log_token_or_destination(caplog):
    from backend.telegram_delivery import TelegramDeliverySettings, deliver_prepared_message

    request = httpx.Request("POST", "https://api.telegram.org/botsecret-token/sendMessage")
    response = httpx.Response(403, request=request)
    post = Mock(side_effect=httpx.HTTPStatusError("forbidden", request=request, response=response))
    settings = TelegramDeliverySettings(bot_token="secret-token", chat_id="-987654321")

    with caplog.at_level(logging.WARNING):
        result = deliver_prepared_message("Prepared message.", "sig-3", settings=settings, post=post)

    assert result["status"] == "failed"
    assert "secret-token" not in caplog.text
    assert "-987654321" not in caplog.text


def test_delivery_endpoint_returns_sender_ack(monkeypatch):
    monkeypatch.setattr(
        "backend.main.deliver_prepared_message",
        lambda message, event_signature: {
            "status": "sent",
            "event_signature": event_signature,
            "message_id": 21,
            "destination": "...1234",
            "detail": message,
        },
    )

    response = TestClient(app).post(
        "/api/telegram-delivery",
        json={"message": "Prepared.", "event_signature": "event-sig"},
    )

    assert response.status_code == 200
    assert response.json()["message_id"] == 21
    assert response.json()["event_signature"] == "event-sig"


def test_delivery_endpoint_rejects_empty_message():
    response = TestClient(app).post(
        "/api/telegram-delivery",
        json={"message": "", "event_signature": "event-sig"},
    )

    assert response.status_code == 422
