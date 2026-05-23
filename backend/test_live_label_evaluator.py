import json
import tempfile
import unittest
from pathlib import Path

from backend.live_label_evaluator import evaluate_live_labels, load_sessions


def write_session(directory, label, name, filtered_values, motion_values=None, rssi_values=None):
    motion_values = motion_values or [0.0] * len(filtered_values)
    rssi_values = rssi_values or [-60] * len(filtered_values)
    path = Path(directory) / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for index, value in enumerate(filtered_values):
            handle.write(
                json.dumps(
                    {
                        "label": label,
                        "seq": index,
                        "rssi": rssi_values[index % len(rssi_values)],
                        "n_subcarriers": 128,
                        "raw_signal": value,
                        "selected_signal": value,
                        "filtered_signal": value,
                        "motion_score": motion_values[index % len(motion_values)],
                    }
                )
                + "\n"
            )
    return path


class TestLiveLabelEvaluator(unittest.TestCase):
    def test_load_sessions_extracts_session_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_session(tmp, "empty", "empty_a", [20.0, 21.0, 20.0, 21.0], rssi_values=[-70, -65])

            sessions = load_sessions(Path(tmp))

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["label"], "empty")
        self.assertEqual(sessions[0]["binary_label"], "empty")
        self.assertEqual(sessions[0]["packets"], 4)
        self.assertAlmostEqual(sessions[0]["filtered_variance"], 0.25)
        self.assertEqual(sessions[0]["rssi_spread"], 5)

    def test_evaluate_live_labels_separates_empty_from_occupied(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_session(tmp, "empty", "empty_a", [20.0, 21.0, 20.0, 21.0])
            write_session(tmp, "empty", "empty_b", [22.0, 22.5, 22.0, 22.5])
            write_session(tmp, "sitting", "sitting_a", [20.0, 24.0, 20.0, 24.0])
            write_session(tmp, "standing", "standing_a", [30.0, 36.0, 30.0, 36.0])
            write_session(tmp, "walking", "walking_a", [18.0, 27.0, 18.0, 27.0])

            report = evaluate_live_labels(Path(tmp))

        self.assertTrue(report["readiness"]["ready"])
        self.assertEqual(report["model"]["feature"], "filtered_variance")
        self.assertEqual(report["evaluation"]["accuracy"], 1.0)
        self.assertEqual(report["confusion"]["empty"]["empty"], 2)
        self.assertEqual(report["confusion"]["occupied"]["occupied"], 3)

    def test_evaluate_live_labels_reports_not_ready_without_enough_empty_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_session(tmp, "empty", "empty_a", [20.0, 21.0, 20.0, 21.0])
            write_session(tmp, "walking", "walking_a", [18.0, 27.0, 18.0, 27.0])

            report = evaluate_live_labels(Path(tmp))

        self.assertFalse(report["readiness"]["ready"])
        self.assertIn("empty", report["readiness"]["needed"])


if __name__ == "__main__":
    unittest.main()
