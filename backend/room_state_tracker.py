"""RuView-inspired online room-state fingerprinting for ESP32 CSI snapshots."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


BAR_ALPHABET = "._:-=+*#"


def fingerprint_to_vector(fingerprint: dict, telemetry: dict, quality: dict) -> list[float]:
    """Convert compact CSI fingerprint + telemetry into a normalized feature vector."""

    bars = str(fingerprint.get("bars") or "")
    values = [_bar_value(char) for char in bars[:16]]
    values.extend([0.0] * (16 - len(values)))

    motion = telemetry.get("motion") or {}
    occupancy = telemetry.get("occupancy") or {}
    values.extend(
        [
            _clamp(float(fingerprint.get("mean", 0.0)) / 64.0),
            _clamp(float(fingerprint.get("spread", 0.0)) / 64.0),
            _clamp(float(motion.get("score", 0.0)) / 12.0),
            _clamp(float(quality.get("fps", 0.0)) / 50.0) if occupancy.get("trusted", True) else 0.0,
        ]
    )
    return [round(value, 4) for value in values]


def build_room_state(snapshot: dict) -> dict:
    """Build a stateless room-state estimate for one dashboard snapshot."""

    telemetry = snapshot.get("telemetry") or {}
    quality = snapshot.get("quality") or {}
    fingerprint = snapshot.get("fingerprint") or {}
    occupancy = telemetry.get("occupancy") or {}
    motion = telemetry.get("motion") or {}
    trusted = bool(occupancy.get("trusted", False)) and quality.get("status") != "WEAK"

    if not trusted:
        label = "signal watch"
        cluster_id = 99
        anomaly = 0.75
    elif occupancy.get("class") == "EMPTY":
        label = "quiet baseline"
        cluster_id = 0
        anomaly = 0.05
    elif motion.get("display_level") == "HIGH":
        label = "active motion"
        cluster_id = 2
        anomaly = 0.35
    else:
        label = "resting occupied"
        cluster_id = 1
        anomaly = 0.15

    return {
        "cluster_id": cluster_id,
        "label": label,
        "distance": 0.0,
        "transitioned": False,
        "trusted": trusted,
        "anomaly_score": anomaly,
        "timeline": _timeline_char(cluster_id),
        "vector": fingerprint_to_vector(fingerprint, telemetry, quality),
    }


@dataclass
class _Centroid:
    center: list[float]
    count: int
    label: str


@dataclass
class OnlineRoomStateTracker:
    """Tiny online k-means tracker based on RuView ADR-077 room fingerprinting."""

    max_clusters: int = 5
    new_cluster_distance: float = 0.8
    alpha: float = 0.08
    centroids: list[_Centroid] = field(default_factory=list)
    current_cluster: int | None = None
    history: list[dict] = field(default_factory=list)
    transitions: dict[str, int] = field(default_factory=dict)

    def observe(self, snapshot: dict) -> dict:
        vector = fingerprint_to_vector(snapshot["fingerprint"], snapshot["telemetry"], snapshot["quality"])
        cluster_id, distance = self._assign(vector)
        prev = self.current_cluster
        transitioned = prev is not None and prev != cluster_id
        if transitioned:
            key = f"{prev}->{cluster_id}"
            self.transitions[key] = self.transitions.get(key, 0) + 1
        self.current_cluster = cluster_id

        label = self._label_for(snapshot, cluster_id)
        self.centroids[cluster_id].label = label
        entry = {
            "cluster_id": cluster_id,
            "label": label,
            "distance": round(distance, 4),
            "transitioned": transitioned,
            "trusted": snapshot["telemetry"].get("occupancy", {}).get("trusted", False),
            "anomaly_score": round(self.anomaly_score(cluster_id), 3),
            "timeline": self.timeline(),
        }
        self.history.append(entry)
        return entry

    def summary(self) -> dict:
        return {
            "clusters": [
                {"cluster_id": index, "label": centroid.label, "count": centroid.count}
                for index, centroid in enumerate(self.centroids)
            ],
            "current_cluster": self.current_cluster,
            "transitions": dict(self.transitions),
            "timeline": self.timeline(),
            "anomaly_score": round(self.anomaly_score(self.current_cluster), 3),
        }

    def anomaly_score(self, cluster_id: int | None) -> float:
        if cluster_id is None or len(self.history) < 3:
            return 0.0
        recent = self.history[-12:]
        matches = sum(1 for item in recent if item["cluster_id"] == cluster_id)
        return 1.0 - (matches / len(recent))

    def timeline(self, width: int = 18) -> str:
        if not self.history:
            return ""
        recent = self.history[-width:]
        return "".join(_timeline_char(item["cluster_id"]) for item in recent)

    def _assign(self, vector: list[float]) -> tuple[int, float]:
        if not self.centroids:
            self.centroids.append(_Centroid(center=list(vector), count=1, label="quiet baseline"))
            return 0, 0.0

        distances = [_distance(vector, centroid.center) for centroid in self.centroids]
        best_id = min(range(len(distances)), key=distances.__getitem__)
        best_distance = distances[best_id]

        if best_distance > self.new_cluster_distance and len(self.centroids) < self.max_clusters:
            cluster_id = len(self.centroids)
            self.centroids.append(_Centroid(center=list(vector), count=1, label=f"state {cluster_id}"))
            return cluster_id, 0.0

        centroid = self.centroids[best_id]
        centroid.count += 1
        centroid.center = [
            round((existing * (1.0 - self.alpha)) + (incoming * self.alpha), 5)
            for existing, incoming in zip(centroid.center, vector, strict=True)
        ]
        return best_id, best_distance

    def _label_for(self, snapshot: dict, cluster_id: int) -> str:
        quality = snapshot.get("quality") or {}
        telemetry = snapshot.get("telemetry") or {}
        occupancy = telemetry.get("occupancy") or {}
        motion = telemetry.get("motion") or {}
        if quality.get("status") == "WEAK" or not occupancy.get("trusted", False):
            return "signal watch"
        if occupancy.get("class") == "EMPTY":
            return "quiet baseline"
        if motion.get("display_level") == "HIGH":
            return "active motion"
        if cluster_id == 0:
            return "known baseline"
        return "resting occupied"


def _bar_value(char: str) -> float:
    index = BAR_ALPHABET.find(char)
    if index < 0:
        return 0.0
    return index / (len(BAR_ALPHABET) - 1)


def _distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _timeline_char(cluster_id: int) -> str:
    return "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[min(cluster_id, 35)]
