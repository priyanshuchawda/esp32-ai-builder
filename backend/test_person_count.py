from backend.person_count import estimate_person_count


def test_person_count_empty_room_is_zero():
    result = estimate_person_count(
        {
            "quality": {"status": "GOOD"},
            "telemetry": {"occupancy": {"class": "EMPTY", "trusted": True}, "motion": {"display_level": "STILL"}},
            "fingerprint": {"spread": 1.2},
        }
    )

    assert result["estimate"] == 0
    assert result["label"] == "empty room"
    assert result["trusted"] is True


def test_person_count_single_occupied_zone():
    result = estimate_person_count(
        {
            "quality": {"status": "GOOD"},
            "telemetry": {"occupancy": {"class": "OCCUPIED", "trusted": True}, "motion": {"display_level": "STILL"}},
            "fingerprint": {"spread": 10.0},
        }
    )

    assert result["estimate"] == 1
    assert result["range"] == "1"
    assert result["confidence"] in {"medium", "high"}


def test_person_count_blocks_weak_quality():
    result = estimate_person_count(
        {
            "quality": {"status": "WEAK"},
            "telemetry": {"occupancy": {"class": "OCCUPIED", "trusted": False}, "motion": {"display_level": "UNSTABLE"}},
            "fingerprint": {"spread": 30.0},
        }
    )

    assert result["trusted"] is False
    assert result["range"] == "unknown"
    assert "signal_quality_not_good" in result["reasons"]


def test_person_count_marks_multi_zone_candidate_conservatively():
    result = estimate_person_count(
        {
            "quality": {"status": "GOOD"},
            "telemetry": {"occupancy": {"class": "OCCUPIED", "trusted": True}, "motion": {"display_level": "HIGH"}},
            "fingerprint": {"spread": 34.0},
            "motion_cadence": {"state": "walking", "trusted": True},
        }
    )

    assert result["estimate"] == 2
    assert result["range"] == "2+"
    assert result["confidence"] == "low"
    assert "single_link_estimate" in result["reasons"]
