import json

from calibration_report import (
    build_readiness,
    evaluate_nearest_centroid,
    load_labeled_windows,
    summarize_labels,
)


def _record(label, signal_mean, signal_std, window_index, sample_count=20):
    return {
        "label": label,
        "session_id": f"session_{label}",
        "mode": "serial",
        "window_index": window_index,
        "features": {
            "rssi_mean": -50.0,
            "rssi_std": 1.0,
            "signal_mean": signal_mean,
            "signal_std": signal_std,
            "signal_variance": signal_std * signal_std,
            "signal_energy": signal_mean * signal_mean,
            "outlier_ratio": 0.0,
            "min_value": signal_mean - 1.0,
            "max_value": signal_mean + 1.0,
            "sample_count": sample_count,
            "missing_or_invalid_count": 0,
        },
        "decision": {"filter": "moving_average", "confidence": 1.0},
    }


def test_load_labeled_windows_reads_jsonl_files(tmp_path):
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    (labels_dir / "empty.jsonl").write_text(
        json.dumps(_record("empty", 10.0, 0.3, 0)) + "\n"
        + json.dumps(_record("empty", 11.0, 0.4, 1)) + "\n",
        encoding="utf-8",
    )
    (labels_dir / "walking.jsonl").write_text(
        json.dumps(_record("walking", 40.0, 4.0, 0)) + "\n",
        encoding="utf-8",
    )

    records = load_labeled_windows(labels_dir)

    assert [record["label"] for record in records] == ["empty", "empty", "walking"]
    assert records[0]["source_file"] == "empty.jsonl"
    assert records[0]["source_line"] == 1


def test_summarize_labels_counts_rows_and_sessions():
    records = [
        _record("empty", 10.0, 0.3, 0),
        _record("empty", 11.0, 0.4, 1),
        _record("walking", 40.0, 4.0, 0),
    ]

    summary = summarize_labels(records)

    assert summary["total_records"] == 3
    assert summary["labels"]["empty"]["records"] == 2
    assert summary["labels"]["empty"]["sessions"] == ["session_empty"]
    assert summary["labels"]["walking"]["records"] == 1


def test_evaluate_nearest_centroid_reports_accuracy_and_confusion():
    records = [
        _record("empty", 10.0, 0.2, 0),
        _record("empty", 11.0, 0.3, 1),
        _record("empty", 12.0, 0.4, 2),
        _record("walking", 40.0, 4.0, 0),
        _record("walking", 41.0, 4.1, 1),
        _record("walking", 42.0, 4.2, 2),
    ]

    report = evaluate_nearest_centroid(records, min_records_per_label=2)

    assert report["eligible"] is True
    assert report["accuracy"] == 1.0
    assert report["test_records"] == 2
    assert report["confusion"]["empty"]["empty"] == 1
    assert report["confusion"]["walking"]["walking"] == 1


def test_evaluate_nearest_centroid_requires_two_labels():
    records = [_record("empty", 10.0, 0.2, 0), _record("empty", 11.0, 0.3, 1)]

    report = evaluate_nearest_centroid(records)

    assert report["eligible"] is False
    assert "at least two labels" in report["reason"]


def test_evaluate_nearest_centroid_ignores_undersized_windows():
    records = [
        _record("sitting", 20.0, 1.0, 0),
        _record("sitting", 21.0, 1.1, 1),
        _record("sitting", 80.0, 8.0, 2, sample_count=4),
        _record("walking", 40.0, 4.0, 0),
        _record("walking", 41.0, 4.1, 1),
    ]

    report = evaluate_nearest_centroid(
        records,
        min_records_per_label=2,
        min_samples_per_window=10,
    )

    assert report["eligible"] is True
    assert report["ignored_records"] == 1
    assert report["train_records"] == 2
    assert report["test_records"] == 2


def test_build_readiness_reports_missing_target_labels():
    records = [
        _record("walking", 40.0, 4.0, 0),
        _record("walking", 41.0, 4.1, 1),
        _record("walking", 42.0, 4.2, 2),
    ]

    readiness = build_readiness(
        records,
        target_labels=["empty", "sitting", "walking"],
        min_records_per_label=3,
    )

    assert readiness["ready"] is False
    assert readiness["labels"]["walking"]["ready"] is True
    assert readiness["labels"]["empty"]["needed"] == 3
    assert readiness["labels"]["sitting"]["needed"] == 3
    assert readiness["next_labels"] == ["empty", "sitting"]


def test_build_readiness_reports_ready_when_targets_have_enough_records():
    records = [
        _record("empty", 10.0, 0.2, 0),
        _record("empty", 11.0, 0.3, 1),
        _record("sitting", 20.0, 1.0, 0),
        _record("sitting", 21.0, 1.1, 1),
    ]

    readiness = build_readiness(
        records,
        target_labels=["empty", "sitting"],
        min_records_per_label=2,
    )

    assert readiness["ready"] is True
    assert readiness["next_labels"] == []


def test_build_readiness_counts_only_usable_windows():
    records = [
        _record("sitting", 20.0, 1.0, 0),
        _record("sitting", 21.0, 1.1, 1),
        _record("sitting", 22.0, 1.2, 2, sample_count=4),
    ]

    readiness = build_readiness(
        records,
        target_labels=["sitting"],
        min_records_per_label=3,
        min_samples_per_window=10,
    )

    assert readiness["ready"] is False
    assert readiness["labels"]["sitting"]["records"] == 2
    assert readiness["labels"]["sitting"]["ignored"] == 1
    assert readiness["labels"]["sitting"]["needed"] == 1
