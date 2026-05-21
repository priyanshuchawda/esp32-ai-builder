import numpy as np
import pytest
from features import calculate_outlier_ratio, extract_features


def test_calculate_outlier_ratio():
    # A clean flat signal has no outliers
    flat_signal = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
    assert calculate_outlier_ratio(flat_signal) == 0.0

    # 1 outlier in a 10-sample signal -> 0.1 ratio
    # Values around 10, one value at 100
    spiked_signal = np.array([10.0, 9.8, 10.1, 10.2, 9.9, 100.0, 10.0, 9.7, 10.3, 10.0])
    ratio = calculate_outlier_ratio(spiked_signal)
    assert pytest.approx(ratio) == 0.1

    # Empty signal check
    assert calculate_outlier_ratio(np.array([])) == 0.0


def test_extract_features():
    rssi = [-50, -51, -50, -49, -50]
    signal = [20.0, 21.0, 20.0, 19.0, 20.0]

    features = extract_features(rssi, signal, missing_count=3)

    assert features["sample_count"] == 5
    assert features["missing_or_invalid_count"] == 3
    assert features["rssi_mean"] == -50.0
    assert features["signal_mean"] == 20.0

    # Variance of [20, 21, 20, 19, 20]:
    # mean is 20
    # squared diffs: [0, 1, 0, 1, 0] -> sum is 2 -> mean is 0.4
    assert pytest.approx(features["signal_variance"]) == 0.4

    # Min & Max
    assert features["min_value"] == 19.0
    assert features["max_value"] == 21.0

    # Energy: 20^2 + 21^2 + 20^2 + 19^2 + 20^2 = 400 + 441 + 400 + 361 + 400 = 2002
    assert features["signal_energy"] == 2002.0

    # Outlier ratio of a quiet signal should be 0.0
    assert features["outlier_ratio"] == 0.0


def test_extract_features_empty():
    features = extract_features([], [], missing_count=2)
    assert features["sample_count"] == 0
    assert features["missing_or_invalid_count"] == 2
    assert features["rssi_mean"] == 0.0
    assert features["signal_mean"] == 0.0
