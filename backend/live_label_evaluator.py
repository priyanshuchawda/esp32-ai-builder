import json
import statistics
from pathlib import Path


OCCUPIED_LABELS = {"sitting", "standing", "walking", "occupied"}


def load_sessions(labels_dir):
    labels_path = Path(labels_dir)
    sessions = []
    for path in sorted(labels_path.glob("*.jsonl")):
        rows = _read_jsonl(path)
        if not rows:
            continue
        label = str(rows[0].get("label", path.stem.split("_")[0])).lower()
        filtered = _values(rows, "filtered_signal")
        selected = _values(rows, "selected_signal")
        raw = _values(rows, "raw_signal")
        motion = _values(rows, "motion_score")
        rssis = _values(rows, "rssi")
        n_subcarriers = [int(row.get("n_subcarriers", 0) or 0) for row in rows]
        sessions.append(
            {
                "file": path.name,
                "label": label,
                "binary_label": "empty" if label == "empty" else "occupied",
                "packets": len(rows),
                "raw_mean": _mean(raw),
                "raw_variance": _variance(raw),
                "selected_mean": _mean(selected),
                "selected_variance": _variance(selected),
                "filtered_mean": _mean(filtered),
                "filtered_variance": _variance(filtered),
                "motion_mean": _mean(motion),
                "motion_max": max(motion) if motion else 0.0,
                "rssi_spread": _spread(rssis),
                "dominant_subcarriers": _mode(n_subcarriers),
            }
        )
    return sessions


def evaluate_live_labels(labels_dir, min_empty_sessions=2, min_occupied_sessions=3):
    sessions = load_sessions(labels_dir)
    empty_sessions = [session for session in sessions if session["binary_label"] == "empty"]
    occupied_sessions = [session for session in sessions if session["binary_label"] == "occupied"]
    readiness = _readiness(empty_sessions, occupied_sessions, min_empty_sessions, min_occupied_sessions)

    model = _fit_threshold(empty_sessions, occupied_sessions)
    predictions = []
    confusion = {
        "empty": {"empty": 0, "occupied": 0},
        "occupied": {"empty": 0, "occupied": 0},
    }
    correct = 0
    for session in sessions:
        predicted = _predict(session, model)
        actual = session["binary_label"]
        predictions.append(
            {
                "file": session["file"],
                "actual": actual,
                "predicted": predicted,
                "feature_value": round(session.get(model["feature"], 0.0), 4),
                "label": session["label"],
            }
        )
        confusion[actual][predicted] += 1
        if actual == predicted:
            correct += 1

    total = len(sessions)
    return {
        "labels_dir": str(Path(labels_dir)),
        "readiness": readiness,
        "model": model,
        "evaluation": {
            "sessions": total,
            "accuracy": round(correct / total, 4) if total else 0.0,
            "correct": correct,
        },
        "confusion": confusion,
        "predictions": predictions,
        "sessions": sessions,
    }


def _read_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _values(rows, key):
    values = []
    for row in rows:
        if key in row and row[key] is not None:
            values.append(float(row[key]))
    return values


def _fit_threshold(empty_sessions, occupied_sessions):
    feature = "filtered_variance"
    if not empty_sessions or not occupied_sessions:
        return {"feature": feature, "threshold": 0.0, "empty_max": 0.0, "occupied_min": 0.0}

    empty_max = max(session[feature] for session in empty_sessions)
    occupied_min = min(session[feature] for session in occupied_sessions)
    threshold = (empty_max + occupied_min) / 2.0
    return {
        "feature": feature,
        "threshold": round(threshold, 4),
        "empty_max": round(empty_max, 4),
        "occupied_min": round(occupied_min, 4),
    }


def _predict(session, model):
    return "occupied" if session.get(model["feature"], 0.0) > model["threshold"] else "empty"


def _readiness(empty_sessions, occupied_sessions, min_empty_sessions, min_occupied_sessions):
    needed = {}
    if len(empty_sessions) < min_empty_sessions:
        needed["empty"] = min_empty_sessions - len(empty_sessions)
    if len(occupied_sessions) < min_occupied_sessions:
        needed["occupied"] = min_occupied_sessions - len(occupied_sessions)
    return {
        "ready": not needed,
        "empty_sessions": len(empty_sessions),
        "occupied_sessions": len(occupied_sessions),
        "needed": needed,
    }


def _mean(values):
    return round(statistics.mean(values), 4) if values else 0.0


def _variance(values):
    return round(statistics.pvariance(values), 4) if len(values) > 1 else 0.0


def _spread(values):
    return round(max(values) - min(values), 4) if values else 0.0


def _mode(values):
    if not values:
        return 0
    return max(set(values), key=lambda value: (values.count(value), value))
