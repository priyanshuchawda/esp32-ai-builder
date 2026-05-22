from app import classify_activity_window


def test_classify_activity_window_skips_when_model_missing():
    assert classify_activity_window({"signal_mean": 10.0}, None) is None


def test_classify_activity_window_returns_prediction_for_eligible_model():
    model = {
        "eligible": True,
        "centroids": {
            "empty": {
                "rssi_mean": -50.0,
                "rssi_std": 1.0,
                "signal_mean": 10.0,
                "signal_std": 0.2,
                "signal_variance": 0.04,
                "signal_energy": 100.0,
                "outlier_ratio": 0.0,
                "min_value": 9.0,
                "max_value": 11.0,
                "sample_count": 20,
                "missing_or_invalid_count": 0,
            },
            "walking": {
                "rssi_mean": -50.0,
                "rssi_std": 1.0,
                "signal_mean": 40.0,
                "signal_std": 4.0,
                "signal_variance": 16.0,
                "signal_energy": 1600.0,
                "outlier_ratio": 0.0,
                "min_value": 39.0,
                "max_value": 41.0,
                "sample_count": 20,
                "missing_or_invalid_count": 0,
            },
        },
    }

    prediction = classify_activity_window(
        {
            "rssi_mean": -50.0,
            "rssi_std": 1.0,
            "signal_mean": 39.0,
            "signal_std": 3.8,
            "signal_variance": 14.44,
            "signal_energy": 1521.0,
            "outlier_ratio": 0.0,
            "min_value": 38.0,
            "max_value": 40.0,
            "sample_count": 20,
            "missing_or_invalid_count": 0,
        },
        model,
    )

    assert prediction["label"] == "walking"
