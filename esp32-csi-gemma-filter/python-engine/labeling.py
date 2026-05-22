import json
import re
import time
from pathlib import Path

LABEL_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def normalize_label(label: str) -> str:
    normalized = label.strip().lower().replace(" ", "_")
    if not LABEL_PATTERN.fullmatch(normalized):
        raise ValueError(
            "label must be 1-64 chars and contain only letters, numbers, underscores, or hyphens"
        )
    return normalized


def build_labeled_window_record(
    *,
    label: str,
    session_id: str,
    mode: str,
    window_index: int,
    features: dict,
    decision: dict,
) -> dict:
    return {
        "label": normalize_label(label),
        "recorded_at": int(time.time() * 1000),
        "session_id": session_id,
        "mode": mode,
        "window_index": window_index,
        "features": features,
        "decision": decision,
    }


def write_labeled_window(labels_dir: str | Path, record: dict) -> Path:
    labels_path = Path(labels_dir)
    labels_path.mkdir(parents=True, exist_ok=True)
    label = normalize_label(record["label"])
    output_path = labels_path / f"{label}.jsonl"
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return output_path
