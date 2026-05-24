"""On-demand Gemma briefing for one captured CSI Observatory state."""

from __future__ import annotations

import json
from typing import Any

from backend import ai_advice as hosted


BRIEFING_SYSTEM_PROMPT = """You write a short judge briefing for a Wi-Fi CSI sensing demo.
You receive one compact ESP-derived scene state and compact calibration readiness.
Do not claim camera vision, true DensePose, identity, or medical-grade vitals.
Use only supplied evidence. Return JSON only, no markdown.

Required JSON object:
{
  "title": "short title",
  "sensing_claim": "one evidence-bounded claim",
  "evidence": ["one to three concrete facts"],
  "calibration_context": "one readiness sentence",
  "limitations": ["one or two honest limitations"],
  "next_action": "one practical next action"
}
"""


def query_judge_briefing(
    observatory: dict[str, Any],
    calibration: dict[str, Any],
    client_factory=None,
) -> dict[str, Any]:
    """Return a hosted Gemma briefing, preserving sensor and calibration gates."""

    if not hosted.GEMINI_API_KEY or hosted.genai is None or hosted.types is None:
        return build_rule_based_briefing(observatory, calibration)

    client = (
        client_factory()
        if client_factory
        else hosted.genai.Client(
            api_key=hosted.GEMINI_API_KEY,
            http_options=hosted.types.HttpOptions(timeout=hosted.GEMINI_HTTP_TIMEOUT_MS),
        )
    )
    contents = json.dumps(
        {"observatory": observatory, "calibration": calibration}, sort_keys=True
    )
    for index, model in enumerate(_hosted_models()):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=hosted.types.GenerateContentConfig(
                    system_instruction=BRIEFING_SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json",
                    thinking_config=_thinking_config(),
                ),
            )
            briefing = _parse_briefing(response.text or "")
            if briefing is not None:
                return {
                    "provider": "gemini",
                    "model": model,
                    "primary_model": hosted.GEMINI_GEMMA_MODEL,
                    "fallback_used": index > 0,
                    **_align_with_evidence(briefing, observatory, calibration),
                }
        except Exception:
            continue

    return build_rule_based_briefing(observatory, calibration)


def build_rule_based_briefing(
    observatory: dict[str, Any], calibration: dict[str, Any]
) -> dict[str, Any]:
    signal = observatory.get("signal") or {}
    visual = observatory.get("visual") or {}
    readiness = calibration.get("readiness") or {}
    missing = list(readiness.get("next_labels") or [])
    quality = str(signal.get("quality") or "UNKNOWN")
    trust = str(visual.get("trust") or "blocked")
    pose = str(visual.get("pose_state") or "unknown").replace("_", " ")
    if quality != "GOOD" or trust in {"weak", "blocked"}:
        claim = "The ESP stream is visible, but there is no trusted activity claim from this snapshot."
    else:
        claim = f"Wi-Fi CSI supports a {pose} activity candidate in this captured snapshot."

    if missing:
        context = f"Calibration is incomplete; the next missing label is {missing[0]}."
        next_action = f"Capture a stable {missing[0]} session before strengthening activity claims."
    else:
        context = "Calibration coverage includes empty, sitting, and walking labels."
        next_action = "Use a new labeled verification run to measure repeatability."

    evidence = [
        f"Signal quality is {quality.lower()} with {trust} display trust.",
        f"{int(signal.get('packets') or 0)} packets were summarized for this event.",
    ]
    return {
        "provider": "rules",
        "model": "rules",
        "primary_model": "rules",
        "fallback_used": False,
        "title": "Captured CSI evidence briefing",
        "sensing_claim": claim,
        "evidence": evidence,
        "calibration_context": context,
        "limitations": [
            "Wi-Fi CSI infers activity changes; it does not provide camera pose or identity."
        ],
        "next_action": next_action,
    }


def _align_with_evidence(
    briefing: dict[str, Any],
    observatory: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    local = build_rule_based_briefing(observatory, calibration)
    quality = str((observatory.get("signal") or {}).get("quality") or "UNKNOWN")
    trust = str((observatory.get("visual") or {}).get("trust") or "blocked")
    aligned = {**briefing}
    aligned["calibration_context"] = local["calibration_context"]
    aligned["limitations"] = list(
        dict.fromkeys([*local["limitations"], *briefing["limitations"]])
    )[:2]
    if quality != "GOOD" or trust in {"weak", "blocked"}:
        aligned["sensing_claim"] = local["sensing_claim"]
        aligned["evidence"] = local["evidence"]
        aligned["next_action"] = local["next_action"]
    return aligned


def _hosted_models() -> list[str]:
    return list(
        dict.fromkeys(
            model
            for model in (
                hosted.GEMINI_GEMMA_MODEL.strip(),
                hosted.GEMINI_GEMMA_FALLBACK_MODEL.strip(),
            )
            if model
        )
    )


def _thinking_config():
    if not hosted.GEMINI_THINKING_LEVEL:
        return None
    return hosted.types.ThinkingConfig(thinking_level=hosted.GEMINI_THINKING_LEVEL)


def _parse_briefing(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    required = {
        "title",
        "sensing_claim",
        "evidence",
        "calibration_context",
        "limitations",
        "next_action",
    }
    if not required.issubset(data):
        return None
    if not isinstance(data["evidence"], list) or not isinstance(data["limitations"], list):
        return None
    data["evidence"] = [str(item) for item in data["evidence"][:3]]
    data["limitations"] = [str(item) for item in data["limitations"][:2]]
    return data
