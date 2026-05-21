import numpy as np


def calculate_outlier_ratio(signal: np.ndarray) -> float:
    """
    Calculates the ratio of outliers in the signal window using standard MAD method.
    """
    if len(signal) == 0:
        return 0.0

    median = np.median(signal)
    mad = np.median(np.abs(signal - median))

    # Scale factor 1.4826 to approximate normal distribution standard deviation
    scale_factor = 1.4826
    sigma = scale_factor * mad

    if sigma < 1e-6:
        # Fallback to standard deviation if MAD is zero
        std = np.std(signal)
        if std < 1e-6:
            return 0.0
        outliers = np.abs(signal - median) > 3.0 * std
    else:
        outliers = np.abs(signal - median) > 3.0 * sigma

    return float(np.sum(outliers) / len(signal))


def extract_features(
    rssi_list: list, signal_list: list, missing_count: int = 0
) -> dict:
    """
    Extracts summary features from the rssi and signal lists for a single window.

    Returns a dictionary of features ready for Gemma prompt formulation.
    """
    sample_count = len(signal_list)

    if sample_count == 0:
        return {
            "rssi_mean": 0.0,
            "rssi_std": 0.0,
            "signal_mean": 0.0,
            "signal_std": 0.0,
            "signal_variance": 0.0,
            "signal_energy": 0.0,
            "outlier_ratio": 0.0,
            "min_value": 0.0,
            "max_value": 0.0,
            "sample_count": 0,
            "missing_or_invalid_count": missing_count,
        }

    rssi_arr = np.array(rssi_list, dtype=float)
    signal_arr = np.array(signal_list, dtype=float)

    # Calculate statistics
    rssi_mean = float(np.mean(rssi_arr))
    rssi_std = float(np.std(rssi_arr))

    signal_mean = float(np.mean(signal_arr))
    signal_std = float(np.std(signal_arr))
    signal_var = float(np.var(signal_arr))

    # Signal Energy = sum of squared values
    signal_energy = float(np.sum(signal_arr**2))

    outlier_ratio = calculate_outlier_ratio(signal_arr)

    min_val = float(np.min(signal_arr))
    max_val = float(np.max(signal_arr))

    return {
        "rssi_mean": round(rssi_mean, 4),
        "rssi_std": round(rssi_std, 4),
        "signal_mean": round(signal_mean, 4),
        "signal_std": round(signal_std, 4),
        "signal_variance": round(signal_var, 4),
        "signal_energy": round(signal_energy, 4),
        "outlier_ratio": round(outlier_ratio, 4),
        "min_value": round(min_val, 4),
        "max_value": round(max_val, 4),
        "sample_count": sample_count,
        "missing_or_invalid_count": missing_count,
    }
