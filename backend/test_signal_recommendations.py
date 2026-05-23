import unittest

from backend.csi_recommendations import build_signal_recommendations


class TestSignalRecommendations(unittest.TestCase):
    def test_recommends_empty_room_calibration_when_gate_is_uncalibrated(self):
        signal_quality = {"status": "WEAK", "reasons": []}
        confidence = {
            "alert_allowed": False,
            "reasons": ["calibration_not_ready"],
        }
        telemetry = {"calibration": {"ready": False, "active": False}}

        recommendations = build_signal_recommendations(signal_quality, confidence, telemetry)

        self.assertEqual(recommendations[0]["code"], "calibrate_empty_room")

    def test_recommends_packet_rate_fix_for_low_fps(self):
        signal_quality = {"status": "WEAK", "fps": 3.2, "reasons": ["low_fps"]}
        recommendations = build_signal_recommendations(signal_quality, {}, {})

        self.assertIn("improve_packet_rate", [item["code"] for item in recommendations])

    def test_recommends_rssi_and_subcarrier_stabilization(self):
        signal_quality = {
            "status": "WEAK",
            "fps": 6.0,
            "reasons": ["rssi_unstable", "mixed_subcarriers"],
        }

        recommendations = build_signal_recommendations(signal_quality, {}, {})

        codes = [item["code"] for item in recommendations]
        self.assertIn("stabilize_rssi", codes)
        self.assertIn("stabilize_csi_mode", codes)

    def test_ready_state_returns_single_ready_recommendation(self):
        signal_quality = {"status": "GOOD", "fps": 12.0, "reasons": []}
        confidence = {"alert_allowed": True, "reasons": []}
        telemetry = {"calibration": {"ready": True}}

        recommendations = build_signal_recommendations(signal_quality, confidence, telemetry)

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]["code"], "ready")


if __name__ == "__main__":
    unittest.main()
