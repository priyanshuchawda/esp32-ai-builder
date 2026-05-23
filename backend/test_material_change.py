from backend.csi_demo_simulator import build_demo_snapshot
from backend.material_change import (
    MaterialChangeTracker,
    build_demo_material_change,
    fingerprint_to_amplitudes,
)


def test_fingerprint_to_amplitudes_is_normalized():
    snapshot = build_demo_snapshot("occupied_still")

    amplitudes = fingerprint_to_amplitudes(snapshot["fingerprint"])

    assert len(amplitudes) == 16
    assert min(amplitudes) >= 0.0
    assert max(amplitudes) <= 1.0


def test_tracker_establishes_baseline_then_detects_absorption_change():
    tracker = MaterialChangeTracker(baseline_frames=3, change_threshold=3, ratio_drop=0.65)
    baseline = [0.8] * 16

    for _ in range(3):
        result = tracker.observe(baseline)

    assert result["baseline_ready"] is True
    changed = tracker.observe([0.25 if index < 6 else 0.8 for index in range(16)])

    assert changed["change_detected"] is True
    assert changed["event_type"] == "added"
    assert changed["material_hint"] == "water/human absorption"
    assert changed["changed_bins"] >= 6


def test_tracker_reports_stable_when_changes_are_small():
    tracker = MaterialChangeTracker(baseline_frames=2, change_threshold=4)
    tracker.observe([0.5] * 16)
    tracker.observe([0.5] * 16)

    result = tracker.observe([0.55] * 16)

    assert result["change_detected"] is False
    assert result["material_hint"] == "stable baseline"


def test_demo_material_change_marks_fall_event_as_large_change():
    snapshot = build_demo_snapshot("fall_event")

    result = build_demo_material_change(snapshot)

    assert result["baseline_ready"] is True
    assert result["change_detected"] is True
    assert result["material_hint"] in {"reflective/metal-like", "water/human absorption", "large object change"}
