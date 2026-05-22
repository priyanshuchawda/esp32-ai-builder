import json

import pytest

from labeling import (
    build_labeled_window_record,
    normalize_label,
    write_labeled_window,
)


def test_normalize_label_accepts_safe_activity_labels():
    assert normalize_label("empty") == "empty"
    assert normalize_label("Sitting Still") == "sitting_still"
    assert normalize_label("standing-up") == "standing-up"


def test_normalize_label_rejects_unsafe_labels():
    with pytest.raises(ValueError):
        normalize_label("../empty")

    with pytest.raises(ValueError):
        normalize_label("")

    with pytest.raises(ValueError):
        normalize_label("a" * 65)


def test_build_labeled_window_record_contains_session_context():
    record = build_labeled_window_record(
        label="walking",
        session_id="session_1",
        mode="serial",
        window_index=2,
        features={"sample_count": 7, "signal_std": 3.2},
        decision={"filter": "median", "confidence": 0.9},
    )

    assert record["label"] == "walking"
    assert record["session_id"] == "session_1"
    assert record["mode"] == "serial"
    assert record["window_index"] == 2
    assert record["features"]["signal_std"] == 3.2
    assert record["decision"]["filter"] == "median"
    assert isinstance(record["recorded_at"], int)


def test_write_labeled_window_appends_jsonl(tmp_path):
    labels_dir = tmp_path / "labels"
    record = build_labeled_window_record(
        label="empty",
        session_id="session_1",
        mode="simulate",
        window_index=0,
        features={"sample_count": 100},
        decision={"filter": "none"},
    )

    path = write_labeled_window(labels_dir, record)
    write_labeled_window(labels_dir, record)

    assert path == labels_dir / "empty.jsonl"
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["label"] == "empty"
