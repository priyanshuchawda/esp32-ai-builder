from backend.csi_demo_simulator import build_demo_snapshot
from backend.room_state_tracker import (
    OnlineRoomStateTracker,
    build_room_state,
    fingerprint_to_vector,
)


def test_fingerprint_to_vector_is_stable_and_numeric():
    snapshot = build_demo_snapshot("occupied_still")

    vector = fingerprint_to_vector(snapshot["fingerprint"], snapshot["telemetry"], snapshot["quality"])

    assert len(vector) == 20
    assert all(isinstance(value, float) for value in vector)
    assert all(0.0 <= value <= 1.0 for value in vector)


def test_tracker_clusters_room_states_and_tracks_transition():
    tracker = OnlineRoomStateTracker(max_clusters=4, new_cluster_distance=0.72)
    empty = build_demo_snapshot("empty_room")
    sitting = build_demo_snapshot("occupied_still")

    first = tracker.observe(empty)
    second = tracker.observe(empty)
    third = tracker.observe(sitting)

    assert first["cluster_id"] == second["cluster_id"]
    assert third["cluster_id"] != first["cluster_id"]
    assert third["transitioned"] is True
    assert tracker.summary()["transitions"]


def test_build_room_state_marks_weak_quality_as_signal_watch():
    snapshot = build_demo_snapshot("weak_live_stream")

    room_state = build_room_state(snapshot)

    assert room_state["label"] == "signal watch"
    assert room_state["trusted"] is False
    assert room_state["anomaly_score"] >= 0.5
