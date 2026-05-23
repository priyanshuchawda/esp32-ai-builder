import unittest

from backend.csi_confidence import evaluate_presence_confidence


class TestPresenceConfidence(unittest.TestCase):
    def test_empty_room_has_zero_confidence(self):
        telemetry = {
            "presence": False,
            "variance": 0.1,
            "effective_presence_threshold": 0.6,
            "calibration": {"ready": True},
        }
        signal_quality = {"status": "GOOD", "reasons": []}

        decision = evaluate_presence_confidence(telemetry, signal_quality)

        self.assertEqual(decision["score"], 0)
        self.assertEqual(decision["level"], "LOW")
        self.assertFalse(decision["alert_allowed"])
        self.assertEqual(decision["label"], "ROOM EMPTY")

    def test_high_confidence_requires_calibration_and_good_signal(self):
        telemetry = {
            "presence": True,
            "variance": 3.0,
            "effective_presence_threshold": 0.8,
            "calibration": {"ready": True},
        }
        signal_quality = {"status": "GOOD", "reasons": []}

        decision = evaluate_presence_confidence(telemetry, signal_quality)

        self.assertGreaterEqual(decision["score"], 90)
        self.assertEqual(decision["level"], "HIGH")
        self.assertTrue(decision["alert_allowed"])
        self.assertEqual(decision["label"], "CONFIRMED HUMAN")

    def test_weak_signal_suppresses_human_claim(self):
        telemetry = {
            "presence": True,
            "variance": 3.0,
            "effective_presence_threshold": 0.8,
            "calibration": {"ready": True},
        }
        signal_quality = {"status": "WEAK", "reasons": ["rssi_unstable"]}

        decision = evaluate_presence_confidence(telemetry, signal_quality)

        self.assertFalse(decision["alert_allowed"])
        self.assertEqual(decision["level"], "MEDIUM")
        self.assertEqual(decision["label"], "UNCONFIRMED MOTION")
        self.assertIn("signal_quality_not_good", decision["reasons"])

    def test_uncalibrated_presence_is_not_alertable(self):
        telemetry = {
            "presence": True,
            "variance": 3.0,
            "effective_presence_threshold": 0.8,
            "calibration": {"ready": False, "active": False},
        }
        signal_quality = {"status": "GOOD", "reasons": []}

        decision = evaluate_presence_confidence(telemetry, signal_quality)

        self.assertFalse(decision["alert_allowed"])
        self.assertEqual(decision["label"], "UNCONFIRMED MOTION")
        self.assertIn("calibration_not_ready", decision["reasons"])


if __name__ == "__main__":
    unittest.main()
