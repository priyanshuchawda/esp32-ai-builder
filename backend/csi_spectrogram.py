"""Compact CSI spectrogram heatmaps inspired by RuView ADR-076."""

from __future__ import annotations


ASCII_SCALE = " .:-=+*#"


def build_spectrogram(frames: list[list[float]], time_bins: int = 24, subcarrier_bins: int = 16) -> dict:
    if not frames:
        return {
            "source": "live_udp_frames",
            "time_bins": 0,
            "subcarrier_bins": subcarrier_bins,
            "rows": [],
            "ascii": "",
            "min": 0.0,
            "max": 0.0,
        }

    selected_frames = _downsample_time(frames, time_bins)
    binned_rows = [_bin_subcarriers(frame, subcarrier_bins) for frame in selected_frames]
    flat = [value for row in binned_rows for value in row]
    minimum = min(flat)
    maximum = max(flat)
    span = maximum - minimum or 1.0
    rows = [[round(((value - minimum) / span) * 100) for value in row] for row in binned_rows]

    return {
        "source": "live_udp_frames",
        "time_bins": len(rows),
        "subcarrier_bins": subcarrier_bins,
        "rows": rows,
        "ascii": "\n".join(_row_to_ascii(row) for row in rows),
        "min": round(minimum, 2),
        "max": round(maximum, 2),
    }


def build_demo_spectrogram(snapshot: dict, time_bins: int = 16, subcarrier_bins: int = 16) -> dict:
    fingerprint = snapshot.get("fingerprint") or {}
    bars = str(fingerprint.get("bars") or "")
    base = [_bar_to_amplitude(char) for char in bars]
    if not base:
        base = [0.0] * subcarrier_bins

    frames = []
    for index in range(time_bins):
        shift = index % len(base)
        shifted = base[shift:] + base[:shift]
        pulse = 1.0 + ((index % 5) * 0.035)
        frames.append([value * pulse for value in shifted])
    spectrogram = build_spectrogram(frames, time_bins=time_bins, subcarrier_bins=subcarrier_bins)
    spectrogram["source"] = "demo_fingerprint"
    return spectrogram


def _downsample_time(frames: list[list[float]], time_bins: int) -> list[list[float]]:
    if len(frames) <= time_bins:
        return [list(frame) for frame in frames]
    step = len(frames) / time_bins
    return [list(frames[min(int(index * step), len(frames) - 1)]) for index in range(time_bins)]


def _bin_subcarriers(frame: list[float], bins: int) -> list[float]:
    if not frame:
        return [0.0] * bins
    if len(frame) <= bins:
        values = [float(value) for value in frame]
        values.extend([values[-1]] * (bins - len(values)))
        return values

    step = len(frame) / bins
    result = []
    for index in range(bins):
        start = int(index * step)
        end = max(start + 1, int((index + 1) * step))
        chunk = frame[start:end]
        result.append(sum(chunk) / len(chunk))
    return result


def _row_to_ascii(row: list[int]) -> str:
    return "".join(ASCII_SCALE[min(len(ASCII_SCALE) - 1, round((value / 100) * (len(ASCII_SCALE) - 1)))] for value in row)


def _bar_to_amplitude(char: str) -> float:
    alphabet = "._:-=+*#"
    index = alphabet.find(char)
    if index < 0:
        return 0.0
    return float(index + 1)
