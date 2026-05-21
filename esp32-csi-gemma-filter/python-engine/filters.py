import numpy as np
from scipy.ndimage import median_filter as scipy_median_filter


def moving_average(signal: np.ndarray, window_size: int) -> np.ndarray:
    """
    Applies a moving average filter to the input signal.
    Uses edge padding to avoid border distortion.
    """
    if len(signal) == 0:
        return np.array([], dtype=float)
    signal_arr = np.array(signal, dtype=float)
    if window_size <= 1 or len(signal_arr) < window_size:
        return np.copy(signal_arr)

    pad_left = window_size // 2
    pad_right = window_size - 1 - pad_left
    padded = np.pad(signal_arr, (pad_left, pad_right), mode="edge")

    kernel = np.ones(window_size) / window_size
    filtered = np.convolve(padded, kernel, mode="valid")
    return filtered[: len(signal_arr)]


def median_filter(signal: np.ndarray, window_size: int) -> np.ndarray:
    """
    Applies a median filter to the input signal using scipy.
    """
    if len(signal) == 0:
        return np.array([], dtype=float)
    signal_arr = np.array(signal, dtype=float)
    if window_size <= 1:
        return np.copy(signal_arr)
    return scipy_median_filter(signal_arr, size=window_size, mode="nearest")


def hampel_filter(
    signal: np.ndarray, window_size: int, threshold: float = 3.0
) -> np.ndarray:
    """
    Applies a Hampel filter to detect and replace outliers with local medians.
    """
    if len(signal) == 0:
        return np.array([], dtype=float)
    signal_arr = np.array(signal, dtype=float)
    n = len(signal_arr)
    if window_size <= 1 or n < window_size:
        return np.copy(signal_arr)

    filtered = np.copy(signal_arr)
    half_window = window_size // 2

    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        window = signal_arr[start:end]

        median = np.median(window)
        mad = np.median(np.abs(window - median))

        sigma = 1.4826 * mad

        if sigma < 1e-6:
            # Fallback to local standard deviation if MAD is zero
            std = np.std(window)
            if std > 1e-6 and np.abs(signal_arr[i] - median) > threshold * std:
                filtered[i] = median
        else:
            if np.abs(signal_arr[i] - median) > threshold * sigma:
                filtered[i] = median

    return filtered


def lowpass_filter(signal: np.ndarray, alpha: float) -> np.ndarray:
    """
    Applies a first-order exponential lowpass filter (EMA).
    y[t] = alpha * x[t] + (1 - alpha) * y[t-1]
    """
    if len(signal) == 0:
        return np.array([], dtype=float)
    signal_arr = np.array(signal, dtype=float)
    alpha = max(0.0, min(1.0, alpha))
    filtered = np.copy(signal_arr)
    for i in range(1, len(filtered)):
        filtered[i] = alpha * signal_arr[i] + (1 - alpha) * filtered[i - 1]
    return filtered


def apply_filter(signal: np.ndarray, decision: dict) -> np.ndarray:
    """
    Applies the mathematical filter corresponding to the advisor's decision.
    """
    if len(signal) == 0:
        return np.array([], dtype=float)

    filter_name = decision.get("filter", "none")
    window_size = int(decision.get("window_size", 5))
    threshold = float(decision.get("outlier_threshold", 3.0))
    alpha = float(decision.get("lowpass_alpha", 0.25))

    if filter_name == "moving_average":
        return moving_average(signal, window_size)
    elif filter_name == "median":
        return median_filter(signal, window_size)
    elif filter_name == "hampel":
        return hampel_filter(signal, window_size, threshold)
    elif filter_name == "lowpass":
        return lowpass_filter(signal, alpha)
    else:
        return np.copy(signal).astype(float)
