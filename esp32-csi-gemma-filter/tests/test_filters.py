import numpy as np
import pytest
from filters import (
    moving_average,
    median_filter,
    hampel_filter,
    lowpass_filter,
    apply_filter,
)


def test_moving_average():
    # Test normal behavior
    signal = np.array([10.0, 10.0, 10.0, 20.0, 10.0, 10.0, 10.0])
    filtered = moving_average(signal, 3)

    assert len(filtered) == len(signal)
    # At index 3, the window is [10, 20, 10], average is 13.333
    assert pytest.approx(filtered[3], abs=1e-3) == 13.3333

    # Test shape preservation with empty signal
    empty = np.array([])
    assert len(moving_average(empty, 3)) == 0

    # Test window size smaller than signal or 1
    assert np.array_equal(moving_average(signal, 1), signal)


def test_median_filter():
    # Test outlier spike removal
    signal = np.array([10.0, 10.0, 100.0, 10.0, 10.0])
    filtered = median_filter(signal, 3)

    assert len(filtered) == len(signal)
    # The outlier 100 should be removed
    assert filtered[2] == 10.0

    empty = np.array([])
    assert len(median_filter(empty, 3)) == 0


def test_hampel_filter():
    # Test Hampel filter outlier replacement
    # A single huge spike at index 3
    signal = np.array([10.0, 10.0, 11.0, 100.0, 9.0, 10.0, 10.0])
    filtered = hampel_filter(signal, window_size=5, threshold=2.0)

    assert len(filtered) == len(signal)
    # Index 3 outlier should be replaced by median (10.0)
    assert filtered[3] == 10.0
    # Clean indices should remain unchanged
    assert filtered[0] == 10.0
    assert filtered[1] == 10.0
    assert filtered[2] == 11.0
    assert filtered[4] == 9.0


def test_lowpass_filter():
    signal = np.array([10.0, 20.0, 30.0])
    alpha = 0.5
    filtered = lowpass_filter(signal, alpha)

    assert len(filtered) == len(signal)
    # y[0] = x[0] = 10.0
    # y[1] = 0.5 * 20.0 + 0.5 * 10.0 = 15.0
    # y[2] = 0.5 * 30.0 + 0.5 * 15.0 = 22.5
    assert filtered[0] == 10.0
    assert filtered[1] == 15.0
    assert filtered[2] == 22.5


def test_apply_filter():
    signal = np.array([10.0, 100.0, 10.0])

    # Test median application
    decision = {
        "filter": "median",
        "window_size": 3,
        "outlier_threshold": 3.0,
        "lowpass_alpha": 0.25,
    }
    filtered = apply_filter(signal, decision)
    assert filtered[1] == 10.0

    # Test lowpass application
    decision_lp = {
        "filter": "lowpass",
        "window_size": 3,
        "outlier_threshold": 3.0,
        "lowpass_alpha": 0.5,
    }
    filtered_lp = apply_filter(signal, decision_lp)
    # y[0] = 10, y[1] = 0.5 * 100 + 0.5 * 10 = 55
    assert filtered_lp[1] == 55.0

    # Test fallback/none
    decision_none = {"filter": "none"}
    assert np.array_equal(apply_filter(signal, decision_none), signal)
