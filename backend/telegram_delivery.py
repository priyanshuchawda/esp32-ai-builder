"""Explicit Telegram delivery with safe operator-facing acknowledgments."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class TelegramDeliverySettings:
    """Local-only Telegram settings for one explicit operator request."""

    bot_token: str = ""
    chat_id: str = ""
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> TelegramDeliverySettings:
        load_dotenv(PROJECT_ROOT / "esp32-csi-gemma-filter" / ".env", override=False)
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            timeout_seconds=_float_env("TELEGRAM_TIMEOUT_SEC", 10.0),
        )

    @property
    def ready(self) -> bool:
        return bool(self.bot_token and self.chat_id)


def _mask_destination(chat_id: str) -> str | None:
    if not chat_id:
        return None
    return f"...{chat_id[-4:]}"


def deliver_prepared_message(
    message: str,
    event_signature: str,
    *,
    settings: TelegramDeliverySettings | None = None,
    post: Callable[..., Any] = httpx.post,
) -> dict[str, Any]:
    """Send an already visible message and expose no Telegram secret values."""

    selected = settings or TelegramDeliverySettings.from_env()
    destination = _mask_destination(selected.chat_id)
    if not selected.ready:
        return {
            "status": "not_configured",
            "event_signature": event_signature,
            "message_id": None,
            "destination": destination,
            "detail": "Telegram credentials are not configured.",
        }

    try:
        response = post(
            f"https://api.telegram.org/bot{selected.bot_token}/sendMessage",
            json={
                "chat_id": selected.chat_id,
                "text": message,
                "disable_notification": False,
            },
            timeout=selected.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        message_id = body.get("result", {}).get("message_id") if body.get("ok") else None
        if not isinstance(message_id, int):
            raise ValueError("Telegram response did not contain a message id.")
    except httpx.HTTPStatusError as exc:
        LOGGER.warning("Telegram delivery rejected: status=%s", exc.response.status_code)
        return {
            "status": "failed",
            "event_signature": event_signature,
            "message_id": None,
            "destination": destination,
            "detail": "Telegram rejected the prepared message.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("Telegram delivery failed: type=%s", type(exc).__name__)
        return {
            "status": "failed",
            "event_signature": event_signature,
            "message_id": None,
            "destination": destination,
            "detail": "Telegram delivery failed.",
        }

    return {
        "status": "sent",
        "event_signature": event_signature,
        "message_id": message_id,
        "destination": destination,
        "detail": "Telegram accepted the prepared message.",
    }
