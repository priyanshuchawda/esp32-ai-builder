"""Calibration readiness adapter and Gemma guidance for existing CSI labels."""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from backend import ai_advice as hosted


ROOT_DIR = Path(__file__).resolve().parents[1]
ENGINE_REPORT_PATH = (
    ROOT_DIR / "esp32-csi-gemma-filter" / "python-engine" / "calibration_report.py"
)
DEFAULT_LABELS_DIR = (
    ROOT_DIR / "esp32-csi-gemma-filter" / "python-engine" / "data" / "labels"
)

CALIBRATION_SYSTEM_PROMPT = """You are the calibration coach for a Wi-Fi CSI sensing demo.
You receive only compact label counts and classifier evaluation, never raw CSI.
Recommend the next labeled capture needed for evidence quality.
Do not claim pose recognition, identity, medical measurements, or camera vision.
Return JSON only, no markdown.

Required JSON object:
{
  "status": "collect | improve | ready",
  "headline": "short operator-facing status",
  "evidence": ["one to three facts from the report"],
  "next_label": "empty | sitting | walking | none",
  "next_action": "one concrete capture or verification action",
  "judge_caption": "one honest sentence for the display"
}
"""


def build_calibration_snapshot(labels_dir: str | Path = DEFAULT_LABELS_DIR) -> dict[str, Any]:
    """Return compact readiness and evaluation output from existing label records."""

    report = _engine_report_module().build_report(labels_dir)
    evaluation = report["evaluation"]
    compact_evaluation = {
        key: evaluation[key]
        for key in (
            "eligible",
            "reason",
            "labels",
            "train_records",
            "test_records",
            "ignored_records",
            "accuracy",
            "confusion",
        )
        if key in evaluation
    }
    return {
        "summary": {
            "total_records": report["summary"]["total_records"],
            "labels": {
                label: {"records": details["records"]}
                for label, details in report["summary"]["labels"].items()
            },
        },
        "readiness": report["readiness"],
        "evaluation": compact_evaluation,
    }


def query_calibration_coach(
    report: dict[str, Any], client_factory=None
) -> dict[str, Any]:
    """Return hosted Gemma calibration advice with deterministic fallback."""

    if not hosted.GEMINI_API_KEY or hosted.genai is None or hosted.types is None:
        return build_rule_based_coach_advice(report)

    client = (
        client_factory()
        if client_factory
        else hosted.genai.Client(
            api_key=hosted.GEMINI_API_KEY,
            http_options=hosted.types.HttpOptions(timeout=hosted.GEMINI_HTTP_TIMEOUT_MS),
        )
    )
    for index, model in enumerate(_hosted_models()):
        try:
            response = client.models.generate_content(
                model=model,
                contents=json.dumps(report, sort_keys=True),
                config=hosted.types.GenerateContentConfig(
                    system_instruction=CALIBRATION_SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json",
                    thinking_config=_thinking_config(),
                ),
            )
            advice = _parse_coach_advice(response.text or "")
            if advice is not None:
                return {
                    "provider": "gemini",
                    "model": model,
                    "primary_model": hosted.GEMINI_GEMMA_MODEL,
                    "fallback_used": index > 0,
                    **_align_with_report(advice, report),
                }
        except Exception:
            continue

    return build_rule_based_coach_advice(report)


def build_rule_based_coach_advice(report: dict[str, Any]) -> dict[str, Any]:
    readiness = report.get("readiness") or {}
    evaluation = report.get("evaluation") or {}
    labels = readiness.get("labels") or {}
    missing = list(readiness.get("next_labels") or [])
    if missing:
        label = str(missing[0])
        needed = int((labels.get(label) or {}).get("needed", 1))
        return _with_rules_metadata(
            {
                "status": "collect",
                "headline": f"Calibration needs {label} evidence.",
                "evidence": [f"{label} needs {needed} more usable windows."],
                "next_label": label,
                "next_action": f"Record a stable {label} session next.",
                "judge_caption": "CSI activity guidance is waiting for complete calibration coverage.",
            }
        )

    accuracy = evaluation.get("accuracy")
    if evaluation.get("eligible") and isinstance(accuracy, (float, int)) and accuracy < 0.75:
        return _with_rules_metadata(
            {
                "status": "improve",
                "headline": "Calibration labels exist, but separation is weak.",
                "evidence": [f"Held-out activity accuracy is {accuracy:.0%}."],
                "next_label": "none",
                "next_action": "Capture cleaner examples for any confused activity class.",
                "judge_caption": "CSI labels are available, but accuracy needs improvement before claims.",
            }
        )

    return _with_rules_metadata(
        {
            "status": "ready",
            "headline": "Calibration coverage is ready for evaluation.",
            "evidence": ["Empty, sitting, and walking labels have usable windows."],
            "next_label": "none",
            "next_action": "Run a live labeled verification session when required.",
            "judge_caption": "Calibration evidence is ready for CSI activity verification.",
        }
    )


@lru_cache(maxsize=1)
def _engine_report_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "esp32_activity_calibration_report", ENGINE_REPORT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load calibration report module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _parse_coach_advice(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_clean_json(text))
    except json.JSONDecodeError:
        return None
    required = {
        "status",
        "headline",
        "evidence",
        "next_label",
        "next_action",
        "judge_caption",
    }
    if not required.issubset(data) or data["status"] not in {
        "collect",
        "improve",
        "ready",
    }:
        return None
    if not isinstance(data["evidence"], list):
        return None
    data["evidence"] = [str(item) for item in data["evidence"][:3]]
    return data


def _align_with_report(advice: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    missing = list((report.get("readiness") or {}).get("next_labels") or [])
    if not missing:
        return {**advice, "next_label": "none"} if advice["status"] == "ready" else advice
    label = str(missing[0])
    if advice["status"] == "collect" and advice["next_label"] == label:
        return advice
    local = build_rule_based_coach_advice(report)
    return {
        **advice,
        "status": local["status"],
        "next_label": local["next_label"],
        "next_action": local["next_action"],
        "judge_caption": local["judge_caption"],
    }


def _clean_json(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    return "\n".join(lines[1:-1]).strip()


def _with_rules_metadata(advice: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "rules",
        "model": "rules",
        "primary_model": "rules",
        "fallback_used": False,
        **advice,
    }
