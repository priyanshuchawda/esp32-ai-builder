import argparse
import json
import math
from pathlib import Path

import config

FEATURE_FIELDS = [
    "rssi_mean",
    "rssi_std",
    "signal_mean",
    "signal_std",
    "signal_variance",
    "signal_energy",
    "outlier_ratio",
    "min_value",
    "max_value",
    "sample_count",
    "missing_or_invalid_count",
]
DEFAULT_TARGET_LABELS = ["empty", "sitting", "walking"]
DEFAULT_MIN_SAMPLES_PER_WINDOW = 10


def load_labeled_windows(labels_dir: str | Path) -> list[dict]:
    labels_path = Path(labels_dir)
    if not labels_path.exists():
        return []

    records = []
    for path in sorted(labels_path.glob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid JSON in {path} line {line_number}: {exc.msg}"
                    ) from exc
                record["source_file"] = path.name
                record["source_line"] = line_number
                records.append(record)
    return records


def summarize_labels(records: list[dict]) -> dict:
    labels: dict[str, dict] = {}
    for record in records:
        label = str(record.get("label", "unknown"))
        entry = labels.setdefault(label, {"records": 0, "sessions": set()})
        entry["records"] += 1
        if record.get("session_id"):
            entry["sessions"].add(str(record["session_id"]))

    return {
        "total_records": len(records),
        "labels": {
            label: {
                "records": entry["records"],
                "sessions": sorted(entry["sessions"]),
            }
            for label, entry in sorted(labels.items())
        },
    }


def evaluate_nearest_centroid(
    records: list[dict],
    *,
    min_records_per_label: int = 3,
    min_samples_per_window: int = DEFAULT_MIN_SAMPLES_PER_WINDOW,
) -> dict:
    usable_records, ignored_records = filter_usable_records(
        records,
        min_samples_per_window=min_samples_per_window,
    )
    grouped = _group_eligible_records(usable_records, min_records_per_label)
    if len(grouped) < 2:
        return {
            "eligible": False,
            "ignored_records": ignored_records,
            "reason": (
                "need at least two labels with "
                f"{min_records_per_label}+ records each"
            ),
        }

    train_records = []
    test_records = []
    for label in sorted(grouped):
        label_records = sorted(
            grouped[label],
            key=lambda record: (
                str(record.get("session_id", "")),
                int(record.get("window_index", 0)),
                int(record.get("recorded_at", 0)),
            ),
        )
        train_records.extend(label_records[:-1])
        test_records.append(label_records[-1])

    centroids = _build_centroids(train_records)
    confusion: dict[str, dict[str, int]] = {
        label: {candidate: 0 for candidate in sorted(grouped)}
        for label in sorted(grouped)
    }
    correct = 0
    predictions = []

    for record in test_records:
        actual = str(record["label"])
        predicted = _predict_label(record, centroids)
        confusion[actual][predicted] += 1
        correct += int(predicted == actual)
        predictions.append(
            {
                "actual": actual,
                "predicted": predicted,
                "session_id": record.get("session_id"),
                "window_index": record.get("window_index"),
            }
        )

    return {
        "eligible": True,
        "labels": sorted(grouped),
        "train_records": len(train_records),
        "test_records": len(test_records),
        "ignored_records": ignored_records,
        "accuracy": round(correct / len(test_records), 4),
        "confusion": confusion,
        "predictions": predictions,
    }


def build_readiness(
    records: list[dict],
    *,
    target_labels: list[str] | None = None,
    min_records_per_label: int = 3,
    min_samples_per_window: int = DEFAULT_MIN_SAMPLES_PER_WINDOW,
) -> dict:
    labels = target_labels or DEFAULT_TARGET_LABELS
    counts: dict[str, int] = {}
    ignored_counts: dict[str, int] = {}
    for record in records:
        label = str(record.get("label", "unknown"))
        if not is_usable_record(record, min_samples_per_window):
            ignored_counts[label] = ignored_counts.get(label, 0) + 1
            continue
        counts[label] = counts.get(label, 0) + 1

    label_status = {}
    next_labels = []
    for label in labels:
        count = counts.get(label, 0)
        needed = max(0, min_records_per_label - count)
        ready = needed == 0
        label_status[label] = {
            "records": count,
            "ignored": ignored_counts.get(label, 0),
            "needed": needed,
            "ready": ready,
        }
        if not ready:
            next_labels.append(label)

    return {
        "ready": not next_labels,
        "min_records_per_label": min_records_per_label,
        "min_samples_per_window": min_samples_per_window,
        "target_labels": labels,
        "labels": label_status,
        "next_labels": next_labels,
    }


def build_report(
    labels_dir: str | Path = config.LABELS_DIR,
    *,
    target_labels: list[str] | None = None,
    min_records_per_label: int = 3,
    min_samples_per_window: int = DEFAULT_MIN_SAMPLES_PER_WINDOW,
) -> dict:
    records = load_labeled_windows(labels_dir)
    return {
        "labels_dir": str(Path(labels_dir)),
        "summary": summarize_labels(records),
        "readiness": build_readiness(
            records,
            target_labels=target_labels,
            min_records_per_label=min_records_per_label,
            min_samples_per_window=min_samples_per_window,
        ),
        "evaluation": evaluate_nearest_centroid(
            records,
            min_records_per_label=min_records_per_label,
            min_samples_per_window=min_samples_per_window,
        ),
    }


def is_usable_record(record: dict, min_samples_per_window: int) -> bool:
    features = record.get("features")
    if not isinstance(features, dict):
        return False
    try:
        return int(features.get("sample_count", 0)) >= min_samples_per_window
    except (TypeError, ValueError):
        return False


def filter_usable_records(
    records: list[dict],
    *,
    min_samples_per_window: int = DEFAULT_MIN_SAMPLES_PER_WINDOW,
) -> tuple[list[dict], int]:
    usable_records = [
        record
        for record in records
        if is_usable_record(record, min_samples_per_window)
    ]
    return usable_records, len(records) - len(usable_records)


def _group_eligible_records(records: list[dict], min_records_per_label: int) -> dict:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        label = record.get("label")
        features = record.get("features")
        if not label or not isinstance(features, dict):
            continue
        grouped.setdefault(str(label), []).append(record)
    return {
        label: label_records
        for label, label_records in grouped.items()
        if len(label_records) >= min_records_per_label
    }


def _feature_vector(record: dict) -> list[float]:
    features = record.get("features", {})
    vector = []
    for field in FEATURE_FIELDS:
        try:
            vector.append(float(features.get(field, 0.0)))
        except (TypeError, ValueError):
            vector.append(0.0)
    return vector


def _build_centroids(records: list[dict]) -> dict[str, list[float]]:
    grouped: dict[str, list[list[float]]] = {}
    for record in records:
        grouped.setdefault(str(record["label"]), []).append(_feature_vector(record))

    centroids = {}
    for label, vectors in grouped.items():
        centroids[label] = [
            sum(vector[index] for vector in vectors) / len(vectors)
            for index in range(len(FEATURE_FIELDS))
        ]
    return centroids


def _predict_label(record: dict, centroids: dict[str, list[float]]) -> str:
    vector = _feature_vector(record)
    distances = {
        label: math.sqrt(
            sum((value - centroid[index]) ** 2 for index, value in enumerate(vector))
        )
        for label, centroid in centroids.items()
    }
    return min(distances, key=lambda label: (distances[label], label))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize labeled CSI calibration data and run a baseline evaluator."
    )
    parser.add_argument(
        "--labels-dir",
        default=config.LABELS_DIR,
        help="Directory containing labeled JSONL files.",
    )
    parser.add_argument(
        "--target-label",
        action="append",
        dest="target_labels",
        help="Target activity label to check. Can be repeated.",
    )
    parser.add_argument(
        "--min-records-per-label",
        type=int,
        default=3,
        help="Minimum records required for each target label.",
    )
    parser.add_argument(
        "--min-samples-per-window",
        type=int,
        default=DEFAULT_MIN_SAMPLES_PER_WINDOW,
        help="Minimum CSI samples required before a labeled window is used.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_report(
                args.labels_dir,
                target_labels=args.target_labels,
                min_records_per_label=args.min_records_per_label,
                min_samples_per_window=args.min_samples_per_window,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
