import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - keeps tests usable before deps install
    load_dotenv = None

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PresenceThresholds:
    min_samples: int = 15
    signal_variance: float = 1.0
    signal_std: float = 0.8
    rssi_std: float = 0.8


@dataclass(frozen=True)
class TelegramSettings:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    cooldown_seconds: int = 300
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "TelegramSettings":
        load_local_env()
        return cls(
            enabled=_env_bool("HUMAN_ALERT_ENABLED", default=False),
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            cooldown_seconds=_env_int("HUMAN_ALERT_COOLDOWN_SEC", default=300),
            timeout_seconds=_env_float("TELEGRAM_TIMEOUT_SEC", default=10.0),
        )

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.bot_token) and bool(self.chat_id)


def load_local_env() -> None:
    if load_dotenv is None:
        return

    engine_env = Path(__file__).with_name(".env")
    root_env = Path(__file__).resolve().parents[1] / ".env"
    for env_path in (engine_env, root_env):
        if env_path.exists():
            load_dotenv(env_path, override=False)


def thresholds_from_env() -> PresenceThresholds:
    load_local_env()
    return PresenceThresholds(
        min_samples=_env_int("HUMAN_MIN_SAMPLES", default=15),
        signal_variance=_env_float("HUMAN_SIGNAL_VARIANCE_THRESHOLD", default=1.0),
        signal_std=_env_float("HUMAN_SIGNAL_STD_THRESHOLD", default=0.8),
        rssi_std=_env_float("HUMAN_RSSI_STD_THRESHOLD", default=0.8),
    )


def detect_human_presence(
    features: dict, thresholds: PresenceThresholds | None = None
) -> bool:
    thresholds = thresholds or thresholds_from_env()
    sample_count = int(features.get("sample_count", 0))
    if sample_count < thresholds.min_samples:
        return False

    signal_variance = float(features.get("signal_variance", 0.0))
    signal_std = float(features.get("signal_std", 0.0))
    rssi_std = float(features.get("rssi_std", 0.0))

    signal_motion = (
        signal_variance >= thresholds.signal_variance
        and signal_std >= thresholds.signal_std
    )
    rssi_motion = signal_std >= thresholds.signal_std and rssi_std >= thresholds.rssi_std
    return signal_motion or rssi_motion


def build_presence_message(features: dict, decision: dict) -> str:
    variance = float(features.get("signal_variance", 0.0))
    signal_std = float(features.get("signal_std", 0.0))
    rssi_std = float(features.get("rssi_std", 0.0))
    selected_filter = decision.get("filter", "unknown")
    confidence = decision.get("confidence", "unknown")
    return (
        "Human presence likely detected. "
        f"variance={variance:.4f}, signal_std={signal_std:.4f}, "
        f"rssi_std={rssi_std:.4f}, filter={selected_filter}, "
        f"confidence={confidence}"
    )


class TelegramPresenceAlerter:
    def __init__(
        self,
        settings: TelegramSettings,
        post: Callable = requests.post,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self._post = post
        self._now = now
        self._last_sent_at: float | None = None

    @classmethod
    def from_env(cls) -> "TelegramPresenceAlerter":
        return cls(TelegramSettings.from_env())

    def send_presence_alert(self, features: dict, decision: dict) -> bool:
        if not self.settings.ready:
            return False

        current_time = self._now()
        if (
            self._last_sent_at is not None
            and current_time - self._last_sent_at < self.settings.cooldown_seconds
        ):
            logger.info("Skipping Telegram alert because cooldown is active.")
            return False

        url = f"https://api.telegram.org/bot{self.settings.bot_token}/sendMessage"
        payload = {
            "chat_id": self.settings.chat_id,
            "text": build_presence_message(features, decision),
            "disable_notification": False,
        }

        try:
            response = self._post(
                url,
                json=payload,
                timeout=self.settings.timeout_seconds,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            response = exc.response
            status_code = getattr(response, "status_code", "unknown")
            reason = getattr(response, "reason", "HTTP error")
            logger.warning(
                "Failed to send Telegram human-presence alert: status=%s reason=%s",
                status_code,
                reason,
            )
            return False
        except requests.RequestException as exc:
            logger.warning(
                "Failed to send Telegram human-presence alert: %s",
                exc.__class__.__name__,
            )
            return False

        self._last_sent_at = current_time
        logger.info("Sent Telegram human-presence alert.")
        return True


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Invalid integer for %s; using default %s", name, default)
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Invalid float for %s; using default %s", name, default)
        return default
