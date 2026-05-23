import unittest

from backend.live_occupancy import classify_occupancy


READY_MODEL = {
    "readiness": {"ready": True},
    "model": {"feature": "filtered_variance", "threshold": 6.3609},
}


class TestLiveOccupancy(unittest.TestCase):
    def test_classifies_empty_below_threshold_when_quality_is_good(self):
        telemetry = {"variance": 4.0}
        quality = {"status": "GOOD", "reasons": []}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "EMPTY")
        self.assertTrue(result["trusted"])

    def test_classifies_occupied_above_threshold_when_quality_is_good(self):
        telemetry = {"variance": 8.0}
        quality = {"status": "GOOD", "reasons": []}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "OCCUPIED")
        self.assertTrue(result["trusted"])

    def test_trusts_occupied_when_weak_quality_has_only_rssi_outliers(self):
        telemetry = {"variance": 8.0}
        quality = {"status": "WEAK", "reasons": ["rssi_outliers"]}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "OCCUPIED")
        self.assertTrue(result["trusted"])

    def test_returns_unknown_above_threshold_when_weak_quality_has_blocking_reason(self):
        telemetry = {"variance": 8.0}
        quality = {"status": "WEAK", "reasons": ["rssi_unstable"]}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "UNKNOWN")
        self.assertFalse(result["trusted"])
        self.assertIn("signal_quality_weak_blocked", result["reasons"])

    def test_returns_unknown_below_threshold_when_signal_quality_is_weak(self):
        telemetry = {"variance": 4.0}
        quality = {"status": "WEAK", "reasons": ["rssi_unstable"]}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "UNKNOWN")
        self.assertFalse(result["trusted"])
        self.assertIn("weak_signal_cannot_confirm_empty", result["reasons"])

    def test_trusts_empty_when_weak_quality_has_only_rssi_outliers(self):
        telemetry = {"variance": 4.0}
        quality = {"status": "WEAK", "reasons": ["rssi_outliers"]}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "EMPTY")
        self.assertTrue(result["trusted"])

    def test_keeps_low_fps_as_unknown_even_when_below_threshold(self):
        telemetry = {"variance": 4.0}
        quality = {"status": "WEAK", "reasons": ["low_fps", "rssi_outliers"]}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "UNKNOWN")
        self.assertFalse(result["trusted"])
        self.assertIn("weak_signal_cannot_confirm_empty", result["reasons"])

    def test_returns_unknown_when_signal_quality_is_bad(self):
        telemetry = {"variance": 8.0}
        quality = {"status": "BAD", "reasons": ["stale_stream"]}

        result = classify_occupancy(telemetry, quality, READY_MODEL)

        self.assertEqual(result["class"], "UNKNOWN")
        self.assertFalse(result["trusted"])
        self.assertIn("signal_quality_bad", result["reasons"])

    def test_returns_unknown_when_evaluator_is_not_ready(self):
        telemetry = {"variance": 8.0}
        quality = {"status": "GOOD", "reasons": []}
        evaluator = {"readiness": {"ready": False}, "model": {"feature": "filtered_variance", "threshold": 6.0}}

        result = classify_occupancy(telemetry, quality, evaluator)

        self.assertEqual(result["class"], "UNKNOWN")
        self.assertFalse(result["trusted"])
        self.assertIn("evaluator_not_ready", result["reasons"])

    def test_uses_telemetry_feature_when_feature_name_is_not_filtered_variance(self):
        telemetry = {"motion_score": 2.5}
        quality = {"status": "GOOD", "reasons": []}
        evaluator = {"readiness": {"ready": True}, "model": {"feature": "motion_score", "threshold": 2.0}}

        result = classify_occupancy(telemetry, quality, evaluator)

        self.assertEqual(result["class"], "OCCUPIED")
        self.assertEqual(result["value"], 2.5)


if __name__ == "__main__":
    unittest.main()
