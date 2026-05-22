import argparse
import json
import math
from pathlib import Path

import config
from calibration_report import (
    DEFAULT_MIN_SAMPLES_PER_WINDOW,
    FEATURE_FIELDS,
    filter_usable_records,
    load_labeled_windows,
)


def build_activity_model(
    records: list[dict],
    *,
    min_records_per_label: int = 3,
    min_samples_per_window: int = DEFAULT_MIN_SAMPLES_PER_WINDOW,
) -> dict:
    usable_records, ignored_records = filter_usable_records(
        records,
        min_samples_per_window=min_samples_per_window,
    )
    grouped: dict[str, list[dict]] = {}
    for record in usable_records:
        label = record.get("label")
        features = record.get("features")
        if not label or not isinstance(features, dict):
            continue
        grouped.setdefault(str(label), []).append(record)

    eligible = {
        label: label_records
        for label, label_records in grouped.items()
        if len(label_records) >= min_records_per_label
    }
    if len(eligible) < 2:
        return {
            "eligible": False,
            "ignored_records": ignored_records,
            "reason": (
                "need at least two labels with "
                f"{min_records_per_label}+ records each"
            ),
            "record_counts": {
                label: len(label_records)
                for label, label_records in sorted(grouped.items())
            },
        }

    centroids = {}
    for label, label_records in sorted(eligible.items()):
        vectors = [_feature_vector(record["features"]) for record in label_records]
        centroid_values = [
            sum(vector[index] for vector in vectors) / len(vectors)
            for index in range(len(FEATURE_FIELDS))
        ]
        centroids[label] = {
            field: round(centroid_values[index], 4)
            for index, field in enumerate(FEATURE_FIELDS)
        }

    return {
        "eligible": True,
        "labels": sorted(eligible),
        "feature_fields": FEATURE_FIELDS,
        "ignored_records": ignored_records,
        "record_counts": {
            label: len(label_records)
            for label, label_records in sorted(eligible.items())
        },
        "centroids": centroids,
    }


def predict_activity(features: dict, model: dict) -> dict:
    if not model.get("eligible"):
        return {
            "eligible": False,
            "reason": model.get("reason", "activity model is not eligible"),
        }

    vector = _feature_vector(features)
    distances = {}
    for label, centroid in model["centroids"].items():
        centroid_vector = [float(centroid.get(field, 0.0)) for field in FEATURE_FIELDS]
        distances[label] = round(
            math.sqrt(
                sum(
                    (value - centroid_vector[index]) ** 2
                    for index, value in enumerate(vector)
                )
            ),
            4,
        )

    label = min(distances, key=lambda candidate: (distances[candidate], candidate))
    return {
        "eligible": True,
        "label": label,
        "distance": distances[label],
        "distances": distances,
    }


def load_activity_model(
    labels_dir: str | Path = config.LABELS_DIR,
    *,
    min_records_per_label: int = 3,
    min_samples_per_window: int = DEFAULT_MIN_SAMPLES_PER_WINDOW,
) -> dict:
    records = load_labeled_windows(labels_dir)
    return build_activity_model(
        records,
        min_records_per_label=min_records_per_label,
        min_samples_per_window=min_samples_per_window,
    )


def _feature_vector(features: dict) -> list[float]:
    vector = []
    for field in FEATURE_FIELDS:
        try:
            vector.append(float(features.get(field, 0.0)))
        except (TypeError, ValueError):
            vector.append(0.0)
    return vector


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local activity model from labeled CSI calibration data."
    )
    parser.add_argument(
        "--labels-dir",
        default=config.LABELS_DIR,
        help="Directory containing labeled JSONL files.",
    )
    parser.add_argument(
        "--min-records-per-label",
        type=int,
        default=3,
        help="Minimum records required before a label is included.",
    )
    parser.add_argument(
        "--min-samples-per-window",
        type=int,
        default=DEFAULT_MIN_SAMPLES_PER_WINDOW,
        help="Minimum CSI samples required before a labeled window is used.",
    )
    args = parser.parse_args()
    model = load_activity_model(
        args.labels_dir,
        min_records_per_label=args.min_records_per_label,
        min_samples_per_window=args.min_samples_per_window,
    )
    print(json.dumps(model, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
