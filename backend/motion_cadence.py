"""Informational motion cadence analysis for compact ESP32 CSI streams."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

import numpy as np


WALKING_MIN_HZ = 0.8
WALKING_MAX_HZ = 2.0
RUNNING_MAX_HZ = 2.5
MIN_SAMPLES = 16
MOTION_FLOOR_STD = 0.08
REGULARITY_TRUST_FLOOR = 0.18


def analyze_motion_cadence(samples: Iterable[Sequence[float] | Mapping[str, float]], quality_status: str | None = None) -> dict:
    """Return a RuView-inspired cadence summary from timestamped motion-energy samples.

    The output is intentionally descriptive only. It reports CSI rhythm strength,
    not identity, diagnosis, or clinical gait quality.
    """

    points = _coerce_samples(samples)
    if len(points) < MIN_SAMPLES:
        return _result("insufficient_data", False, 0.0, 0.0, 0.0, 0.0, len(points), "too_few_samples")

    timestamps = np.array([point[0] for point in points], dtype=float)
    values = np.array([point[1] for point in points], dtype=float)
    fps = _estimate_fps(timestamps)
    centered = values - float(np.mean(values))
    signal_std = float(np.std(centered))

    if fps <= 0.0 or signal_std < MOTION_FLOOR_STD:
        trusted = quality_status == "GOOD"
        return _result("stationary", trusted, 0.0, 0.0, 0.0, 0.0, len(points), "low_motion_energy")

    window = np.hanning(len(centered))
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), d=1.0 / fps)
    power = np.abs(spectrum) ** 2
    band = (freqs >= WALKING_MIN_HZ) & (freqs <= RUNNING_MAX_HZ)

    if not bool(np.any(band)):
        return _result("moving_irregular", False, 0.0, 0.0, 0.0, 0.0, len(points), "cadence_band_unavailable")

    band_indices = np.flatnonzero(band)
    peak_index = int(band_indices[int(np.argmax(power[band]))])
    dominant_hz = float(freqs[peak_index])
    total_power = float(np.sum(power[band]))
    peak_power = float(power[peak_index])
    regularity = peak_power / total_power if total_power > 0 else 0.0
    stride_regularity = _stride_regularity(centered, fps, dominant_hz)
    cadence_spm = dominant_hz * 60.0

    if dominant_hz <= WALKING_MAX_HZ and regularity >= REGULARITY_TRUST_FLOOR:
        state = "walking"
    elif dominant_hz <= RUNNING_MAX_HZ and regularity >= REGULARITY_TRUST_FLOOR:
        state = "running"
    else:
        state = "moving_irregular"

    trusted = quality_status == "GOOD" and state in {"walking", "running"} and stride_regularity >= 0.08
    return _result(
        state,
        trusted,
        cadence_spm,
        dominant_hz,
        regularity,
        stride_regularity,
        len(points),
        "quality_good" if trusted else _trust_reason(quality_status, regularity, stride_regularity),
    )


def build_demo_motion_cadence(snapshot: dict) -> dict:
    scenario = str(snapshot.get("scenario") or "")
    quality_status = str((snapshot.get("quality") or {}).get("status") or "")
    if scenario == "walking":
        return _result("walking", quality_status == "GOOD", 96.0, 1.6, 0.72, 0.64, 125, "quality_good")
    if scenario == "fall_event":
        return _result("moving_irregular", quality_status == "GOOD", 0.0, 0.0, 0.12, 0.05, 60, "impact_like_irregular_motion")
    if scenario == "weak_live_stream":
        return _result("signal_watch", False, 0.0, 0.0, 0.0, 0.0, 0, "signal_quality_not_good")
    return _result("stationary", quality_status == "GOOD", 0.0, 0.0, 0.0, 0.0, 80, "low_motion_energy")


def _coerce_samples(samples: Iterable[Sequence[float] | Mapping[str, float]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for sample in samples:
        try:
            if isinstance(sample, Mapping):
                timestamp = float(sample.get("timestamp", sample.get("time", 0.0)))
                value = float(sample.get("value", sample.get("motion", 0.0)))
            else:
                timestamp = float(sample[0])
                value = float(sample[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(timestamp) and math.isfinite(value):
            points.append((timestamp, value))
    points.sort(key=lambda item: item[0])
    return points


def _estimate_fps(timestamps: np.ndarray) -> float:
    deltas = np.diff(timestamps)
    positive = deltas[deltas > 0.0]
    if len(positive) == 0:
        return 0.0
    median_delta = float(np.median(positive))
    if median_delta <= 0.0:
        return 0.0
    return min(100.0, max(1.0, 1.0 / median_delta))


def _stride_regularity(values: np.ndarray, fps: float, dominant_hz: float) -> float:
    if dominant_hz <= 0.0:
        return 0.0
    lag = max(1, int(round(fps / dominant_hz)))
    if lag >= len(values) - 1:
        return 0.0
    first = values[:-lag]
    second = values[lag:]
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 0.0:
        return 0.0
    return max(0.0, min(1.0, float(np.dot(first, second) / denominator)))


def _trust_reason(quality_status: str | None, regularity: float, stride_regularity: float) -> str:
    if quality_status != "GOOD":
        return "signal_quality_not_good"
    if regularity < REGULARITY_TRUST_FLOOR:
        return "low_cadence_regularity"
    if stride_regularity < 0.08:
        return "low_stride_regularity"
    return "motion_irregular"


def _result(
    state: str,
    trusted: bool,
    cadence_spm: float,
    dominant_frequency_hz: float,
    regularity: float,
    stride_regularity: float,
    sample_count: int,
    trust_reason: str,
) -> dict:
    return {
        "state": state,
        "trusted": trusted,
        "cadence_spm": round(cadence_spm, 1),
        "dominant_frequency_hz": round(dominant_frequency_hz, 3),
        "regularity": round(regularity, 3),
        "stride_regularity": round(stride_regularity, 3),
        "sample_count": sample_count,
        "trust_reason": trust_reason,
    }
