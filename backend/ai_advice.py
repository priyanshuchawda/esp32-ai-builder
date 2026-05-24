"""Gemma-backed explanation layer for compact CSI observatory summaries."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised when optional SDK is absent
    genai = None
    types = None


load_dotenv(Path("esp32-csi-gemma-filter/.env"), override=False)
load_dotenv(Path(".env"), override=False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_GEMMA_MODEL = os.getenv("GEMINI_GEMMA_MODEL", "gemma-4-31b-it").strip()
GEMINI_GEMMA_FALLBACK_MODEL = os.getenv(
    "GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it"
).strip()
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "high").strip()
GEMINI_HTTP_TIMEOUT_MS = int(os.getenv("GEMINI_HTTP_TIMEOUT_MS", "10000"))

SYSTEM_PROMPT = """You explain Wi-Fi CSI room-sensing output for a judge demo.
You never claim camera vision, identity, medical diagnosis, or true DensePose.
You receive compact metrics only, never raw CSI samples.
Return JSON only, no markdown.

Required JSON object:
{
  "status": "trusted | weak | blocked",
  "room_interpretation": "short factual interpretation",
  "why": ["one to three concrete signal reasons"],
  "next_action": "one concrete action",
  "judge_caption": "one sentence for a demo screen",
  "telegram_message": "short alert-safe message",
  "confidence": 0.0
}
"""


def build_event_signature(observatory: dict[str, Any]) -> str:
    signal = observatory.get("signal") or {}
    visual = observatory.get("visual") or {}
    persons = observatory.get("persons") or {}
    motion = observatory.get("motion") or {}
    values = (
        observatory.get("source") or "unknown",
        signal.get("quality") or "UNKNOWN",
        visual.get("trust") or "blocked",
        visual.get("pose_state") or "unknown",
        persons.get("range") or "unknown",
        motion.get("state") or "unknown",
    )
    return "|".join(str(value) for value in values)


def query_ai_advice(observatory: dict[str, Any], client_factory=None) -> dict[str, Any]:
    """Return Gemma advice for compact observatory state, with rules fallback."""

    if not GEMINI_API_KEY or genai is None or types is None:
        return build_rule_based_advice(observatory)

    client = (
        client_factory()
        if client_factory
        else genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS),
        )
    )
    primary_model = GEMINI_GEMMA_MODEL
    for index, model in enumerate(_hosted_models()):
        fallback_used = index > 0
        try:
            response = client.models.generate_content(
                model=model,
                contents=json.dumps(_compact_observatory(observatory), sort_keys=True),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json",
                    thinking_config=_thinking_config(),
                ),
            )
            advice = _parse_advice(response.text or "")
            if advice is not None:
                advice = _align_with_trust_gate(advice, observatory)
                return _with_metadata(
                    advice,
                    provider="gemini",
                    model=model,
                    primary_model=primary_model,
                    fallback_used=fallback_used,
                )
        except Exception:
            continue

    return build_rule_based_advice(observatory)


def build_rule_based_advice(observatory: dict[str, Any]) -> dict[str, Any]:
    signal = observatory.get("signal") or {}
    visual = observatory.get("visual") or {}
    persons = observatory.get("persons") or {}
    motion = observatory.get("motion") or {}

    quality = str(signal.get("quality") or "UNKNOWN")
    trust = str(visual.get("trust") or "blocked")
    pose_state = str(visual.get("pose_state") or "unknown")
    reasons = _humanize_reasons(
        list(visual.get("reasons") or []) + list(signal.get("reasons") or [])
    )

    if quality != "GOOD" or trust in {"weak", "blocked"}:
        status = "weak"
        interpretation = "The ESP32 stream is visible, but the signal is not trusted enough for a room-state claim."
        next_action = (
            "Improve packet rate and RSSI stability before trusting the avatar."
        )
        caption = "Gemma-ready rules blocked the claim because RF quality is weak."
    elif persons.get("range") == "0" or pose_state == "none":
        status = "trusted"
        interpretation = "The current CSI summary matches an empty-room baseline."
        next_action = "Keep this as the calibration reference."
        caption = "Trusted RF baseline: no occupied zone detected."
    else:
        status = "trusted"
        interpretation = f"The CSI summary supports a {pose_state.replace('_', ' ')} activity visualization."
        next_action = "Keep the ESP and router positions stable while collecting more labeled windows."
        caption = "Trusted Wi-Fi CSI activity state rendered in Observatory mode."

    if not reasons:
        reasons = [
            f"quality {quality.lower()}",
            f"motion {str(motion.get('display_level') or 'unknown').lower()}",
        ]

    return _with_metadata(
        {
            "status": status,
            "room_interpretation": interpretation,
            "why": reasons[:3],
            "next_action": next_action,
            "judge_caption": caption,
            "telegram_message": _telegram_message(status, interpretation),
            "confidence": 1.0 if status == "trusted" else 0.45,
        },
        provider="rules",
        model="rules",
        primary_model="rules",
        fallback_used=False,
    )


def _hosted_models() -> list[str]:
    models: list[str] = []
    for model in [GEMINI_GEMMA_MODEL, GEMINI_GEMMA_FALLBACK_MODEL]:
        model = (model or "").strip()
        if model and model not in models:
            models.append(model)
    return models


def _thinking_config():
    if not GEMINI_THINKING_LEVEL:
        return None
    return types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)


def _compact_observatory(observatory: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": observatory.get("source"),
        "truth_label": observatory.get("truth_label"),
        "visual": observatory.get("visual"),
        "persons": observatory.get("persons"),
        "signal": observatory.get("signal"),
        "vitals": observatory.get("vitals"),
        "motion": observatory.get("motion"),
    }


def _parse_advice(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_clean_json(text))
    except json.JSONDecodeError:
        return None
    required = {
        "status",
        "room_interpretation",
        "why",
        "next_action",
        "judge_caption",
        "telegram_message",
        "confidence",
    }
    if not required.issubset(data):
        return None
    if data["status"] not in {"trusted", "weak", "blocked"}:
        return None
    if not isinstance(data["why"], list):
        return None
    data["why"] = [str(reason) for reason in data["why"][:3]]
    data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
    return data


def _align_with_trust_gate(
    advice: dict[str, Any], observatory: dict[str, Any]
) -> dict[str, Any]:
    signal = observatory.get("signal") or {}
    visual = observatory.get("visual") or {}
    persons = observatory.get("persons") or {}

    quality = str(signal.get("quality") or "UNKNOWN")
    trust = str(visual.get("trust") or "blocked")
    pose_state = str(visual.get("pose_state") or "unknown")
    is_empty = persons.get("range") == "0" or pose_state == "none"

    if quality != "GOOD" or trust in {"weak", "blocked"}:
        if advice["status"] == "trusted":
            gated = build_rule_based_advice(observatory)
            advice = {**advice}
            advice["status"] = "weak" if trust != "blocked" else "blocked"
            advice["room_interpretation"] = gated["room_interpretation"]
            advice["next_action"] = gated["next_action"]
            advice["judge_caption"] = gated["judge_caption"]
            advice["telegram_message"] = gated["telegram_message"]
            advice["confidence"] = min(float(advice["confidence"]), 0.55)
            advice["why"] = _prepend_reason(advice["why"], f"quality {quality.lower()}")
        return advice

    if is_empty and advice["status"] != "trusted":
        advice = {**advice}
        advice["status"] = "trusted"
        advice["room_interpretation"] = (
            "The compact CSI state supports a trusted empty-room baseline."
        )
        advice["judge_caption"] = "Trusted RF baseline: no occupied zone detected."
        advice["telegram_message"] = "Trusted CSI: room appears empty."
        advice["next_action"] = "Keep this run as a calibration reference."
        advice["why"] = _prepend_reason(advice["why"], "empty room baseline trusted")
        advice["confidence"] = max(float(advice["confidence"]), 0.8)
    return advice


def _prepend_reason(reasons: list[str], reason: str) -> list[str]:
    return list(dict.fromkeys([reason, *[str(item) for item in reasons if item]]))[:3]


def _clean_json(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _with_metadata(
    advice: dict[str, Any],
    *,
    provider: str,
    model: str,
    primary_model: str,
    fallback_used: bool,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "primary_model": primary_model,
        "fallback_used": fallback_used,
        **advice,
    }


def _humanize_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reason.replace("_", " ") for reason in reasons if reason))


def _telegram_message(status: str, interpretation: str) -> str:
    prefix = "Trusted CSI" if status == "trusted" else "CSI quality watch"
    return f"{prefix}: {interpretation}"
