"""RuView-inspired material/object change detection from compact CSI fingerprints."""

from __future__ import annotations

from dataclasses import dataclass, field


BAR_ALPHABET = "._:-=+*#"


def fingerprint_to_amplitudes(fingerprint: dict) -> list[float]:
    bars = str(fingerprint.get("bars") or "")
    values = []
    for char in bars[:16]:
        index = BAR_ALPHABET.find(char)
        values.append(0.0 if index < 0 else round(index / (len(BAR_ALPHABET) - 1), 4))
    values.extend([0.0] * (16 - len(values)))
    return values


def build_demo_material_change(snapshot: dict) -> dict:
    scenario = snapshot.get("scenario", "")
    current = fingerprint_to_amplitudes(snapshot.get("fingerprint") or {})
    baseline = _demo_baseline()
    result = compare_material_change(
        baseline,
        current,
        baseline_ready=True,
        samples=8,
        change_threshold=3,
    )
    if scenario == "empty_room":
        result["change_detected"] = False
        result["event_type"] = "stable"
        result["material_hint"] = "stable baseline"
        result["changed_bins"] = 0
    return result


@dataclass
class MaterialChangeTracker:
    baseline_frames: int = 12
    change_threshold: int = 4
    null_threshold: float = 0.18
    ratio_drop: float = 0.55
    ratio_rise: float = 1.75
    baseline_sum: list[float] = field(default_factory=list)
    baseline_count: int = 0
    baseline: list[float] = field(default_factory=list)

    def observe(self, amplitudes: list[float]) -> dict:
        values = [float(value) for value in amplitudes[:16]]
        values.extend([0.0] * (16 - len(values)))

        if self.baseline_count < self.baseline_frames:
            self._update_baseline(values)
            return compare_material_change(
                self.baseline,
                values,
                baseline_ready=self.baseline_count >= self.baseline_frames,
                samples=self.baseline_count,
                change_threshold=self.change_threshold,
                null_threshold=self.null_threshold,
                ratio_drop=self.ratio_drop,
                ratio_rise=self.ratio_rise,
            )

        return compare_material_change(
            self.baseline,
            values,
            baseline_ready=True,
            samples=self.baseline_count,
            change_threshold=self.change_threshold,
            null_threshold=self.null_threshold,
            ratio_drop=self.ratio_drop,
            ratio_rise=self.ratio_rise,
        )

    def _update_baseline(self, values: list[float]) -> None:
        if not self.baseline_sum:
            self.baseline_sum = [0.0] * len(values)
        self.baseline_count += 1
        for index, value in enumerate(values):
            self.baseline_sum[index] += value
        self.baseline = [round(value / self.baseline_count, 4) for value in self.baseline_sum]


def compare_material_change(
    baseline: list[float],
    current: list[float],
    *,
    baseline_ready: bool,
    samples: int,
    change_threshold: int,
    null_threshold: float = 0.18,
    ratio_drop: float = 0.55,
    ratio_rise: float = 1.75,
) -> dict:
    if not baseline_ready or not baseline:
        return _result(False, "collecting_baseline", "collecting baseline", 0, [], [], samples, baseline_ready)

    new_nulls = []
    removed_nulls = []
    amplitude_changes = []
    drop_changes = []
    rise_changes = []
    changed_indices = []

    for index, (base, value) in enumerate(zip(baseline, current, strict=True)):
        base_null = base <= null_threshold
        current_null = value <= null_threshold
        if current_null and not base_null:
            new_nulls.append(index)
            changed_indices.append(index)
            continue
        if base_null and not current_null:
            removed_nulls.append(index)
            changed_indices.append(index)
            continue
        if not base_null and not current_null:
            ratio = value / max(base, 0.001)
            if ratio < ratio_drop or ratio > ratio_rise:
                amplitude_changes.append(index)
                if ratio < ratio_drop:
                    drop_changes.append(index)
                else:
                    rise_changes.append(index)
                changed_indices.append(index)

    changed_bins = len(set(changed_indices))
    if changed_bins < change_threshold:
        return _result(False, "stable", "stable baseline", changed_bins, new_nulls, removed_nulls, samples, baseline_ready)

    event_type = _event_type(new_nulls, removed_nulls, amplitude_changes, drop_changes, rise_changes, change_threshold)
    material_hint = _material_hint(new_nulls, removed_nulls, amplitude_changes, drop_changes, len(current))
    return _result(True, event_type, material_hint, changed_bins, new_nulls, removed_nulls, samples, baseline_ready)


def _event_type(
    new_nulls: list[int],
    removed_nulls: list[int],
    amplitude_changes: list[int],
    drop_changes: list[int],
    rise_changes: list[int],
    change_threshold: int,
) -> str:
    if len(new_nulls) > len(removed_nulls):
        return "added"
    if len(removed_nulls) > len(new_nulls):
        return "removed"
    if len(drop_changes) >= change_threshold:
        return "added"
    if len(rise_changes) >= change_threshold:
        return "removed"
    if amplitude_changes:
        return "changed"
    return "moved"


def _material_hint(
    new_nulls: list[int],
    removed_nulls: list[int],
    amplitude_changes: list[int],
    drop_changes: list[int],
    total_bins: int,
) -> str:
    if len(new_nulls) >= max(3, total_bins // 4) or len(drop_changes) >= max(3, total_bins // 4):
        return "water/human absorption"
    if len(removed_nulls) >= max(3, total_bins // 4):
        return "object removed"
    if len(amplitude_changes) >= max(5, total_bins // 2):
        return "large object change"
    if new_nulls:
        return "reflective/metal-like"
    return "broad amplitude shift"


def _result(
    change_detected: bool,
    event_type: str,
    material_hint: str,
    changed_bins: int,
    new_nulls: list[int],
    removed_nulls: list[int],
    samples: int,
    baseline_ready: bool,
) -> dict:
    return {
        "baseline_ready": baseline_ready,
        "samples": samples,
        "change_detected": change_detected,
        "event_type": event_type,
        "material_hint": material_hint,
        "changed_bins": changed_bins,
        "new_nulls": len(new_nulls),
        "removed_nulls": len(removed_nulls),
        "null_map": _null_map(new_nulls, removed_nulls),
    }


def _null_map(new_nulls: list[int], removed_nulls: list[int], bins: int = 16) -> str:
    chars = ["." for _ in range(bins)]
    for index in new_nulls:
        if index < bins:
            chars[index] = "X"
    for index in removed_nulls:
        if index < bins:
            chars[index] = "O"
    return "".join(chars)


def _demo_baseline() -> list[float]:
    return [0.72, 0.72, 0.76, 0.72, 0.72, 0.76, 0.72, 0.72, 0.72, 0.76, 0.72, 0.72, 0.76, 0.72, 0.72, 0.72]
