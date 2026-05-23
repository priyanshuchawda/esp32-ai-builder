import math

from backend.motion_cadence import analyze_motion_cadence, build_demo_motion_cadence


def _sine_samples(freq_hz: float, *, fps: float = 50.0, seconds: float = 5.0) -> list[tuple[float, float]]:
    total = int(fps * seconds)
    return [
        (index / fps, 8.0 + 3.0 * math.sin(2.0 * math.pi * freq_hz * index / fps))
        for index in range(total)
    ]


def test_motion_cadence_reports_insufficient_data():
    result = analyze_motion_cadence([(0.0, 1.0), (0.1, 1.1)])

    assert result["state"] == "insufficient_data"
    assert result["trusted"] is False
    assert result["cadence_spm"] == 0.0


def test_motion_cadence_classifies_stationary_low_variation():
    samples = [(index * 0.05, 4.0 + (0.01 if index % 2 else 0.0)) for index in range(120)]

    result = analyze_motion_cadence(samples, quality_status="GOOD")

    assert result["state"] == "stationary"
    assert result["trusted"] is True
    assert result["cadence_spm"] == 0.0


def test_motion_cadence_finds_walking_rhythm():
    result = analyze_motion_cadence(_sine_samples(1.6), quality_status="GOOD")

    assert result["state"] == "walking"
    assert result["trusted"] is True
    assert 88.0 <= result["cadence_spm"] <= 104.0
    assert result["dominant_frequency_hz"] > 1.3
    assert result["regularity"] > 0.25


def test_demo_motion_cadence_matches_walking_scenario():
    result = build_demo_motion_cadence({"scenario": "walking", "quality": {"status": "GOOD"}})

    assert result["state"] == "walking"
    assert result["trusted"] is True
    assert result["cadence_spm"] >= 80.0
