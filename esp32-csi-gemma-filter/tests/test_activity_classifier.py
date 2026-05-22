from activity_classifier import build_activity_model, predict_activity


def _record(label, signal_mean, signal_std, window_index):
    return {
        "label": label,
        "session_id": f"session_{label}",
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
            "sample_count": 20,
            "missing_or_invalid_count": 0,
        },
    }


def test_build_activity_model_requires_two_labels():
    records = [_record("walking", 40.0, 4.0, 0), _record("walking", 41.0, 4.1, 1)]

    model = build_activity_model(records, min_records_per_label=2)

    assert model["eligible"] is False
    assert "at least two labels" in model["reason"]


def test_build_activity_model_creates_centroids_for_eligible_labels():
    records = [
        _record("empty", 10.0, 0.2, 0),
        _record("empty", 12.0, 0.4, 1),
        _record("walking", 40.0, 4.0, 0),
        _record("walking", 42.0, 4.2, 1),
    ]

    model = build_activity_model(records, min_records_per_label=2)

    assert model["eligible"] is True
    assert model["labels"] == ["empty", "walking"]
    assert model["record_counts"] == {"empty": 2, "walking": 2}
    assert model["centroids"]["empty"]["signal_mean"] == 11.0
    assert model["centroids"]["walking"]["signal_std"] == 4.1


def test_predict_activity_returns_nearest_label_with_distances():
    records = [
        _record("empty", 10.0, 0.2, 0),
        _record("empty", 12.0, 0.4, 1),
        _record("walking", 40.0, 4.0, 0),
        _record("walking", 42.0, 4.2, 1),
    ]
    model = build_activity_model(records, min_records_per_label=2)

    prediction = predict_activity(
        {
            "rssi_mean": -50.0,
            "rssi_std": 1.0,
            "signal_mean": 41.0,
            "signal_std": 4.1,
            "signal_variance": 16.81,
            "signal_energy": 1681.0,
            "outlier_ratio": 0.0,
            "min_value": 40.0,
            "max_value": 42.0,
            "sample_count": 20,
            "missing_or_invalid_count": 0,
        },
        model,
    )

    assert prediction["label"] == "walking"
    assert prediction["distance"] == prediction["distances"]["walking"]
    assert prediction["distances"]["walking"] < prediction["distances"]["empty"]
