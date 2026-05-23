import math
import unittest

from backend.csi_calibration import PresenceCalibration
from frontend.app import RuViewDSP


class TestPresenceCalibration(unittest.TestCase):
    def test_calibration_learns_baseline_and_reports_ready(self):
        calibration = PresenceCalibration(min_samples=5, multiplier=4.0, min_threshold=0.6)

        for sample in [10.0, 10.1, 9.9, 10.05, 9.95]:
            calibration.add_sample(sample)

        summary = calibration.summary()
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["samples"], 5)
        self.assertAlmostEqual(summary["baseline_mean"], 10.0, delta=0.1)
        self.assertGreaterEqual(summary["threshold"], 0.6)

    def test_calibration_threshold_rises_above_noisy_empty_room(self):
        calibration = PresenceCalibration(min_samples=6, multiplier=4.0, min_threshold=0.6)

        for sample in [10.0, 13.0, 8.0, 12.5, 9.0, 11.5]:
            calibration.add_sample(sample)

        summary = calibration.summary()
        self.assertTrue(summary["ready"])
        self.assertGreater(summary["baseline_variance"], 2.0)
        self.assertGreater(summary["threshold"], 2.0)

    def test_dsp_uses_calibrated_threshold_after_empty_room_capture(self):
        dsp = RuViewDSP(fps=25.0)
        dsp.start_presence_calibration(target_samples=30)

        for sample in [25.0 + 0.03 * math.sin(i) for i in range(40)]:
            dsp.add_sample(sample)

        telemetry = dsp.process_telemetry(presence_threshold=0.1, fall_threshold=12.0)

        self.assertTrue(telemetry["calibration"]["ready"])
        self.assertFalse(telemetry["calibration"]["active"])
        self.assertGreaterEqual(telemetry["effective_presence_threshold"], 0.6)
        self.assertFalse(telemetry["presence"])

    def test_dsp_detects_motion_above_calibrated_baseline(self):
        dsp = RuViewDSP(fps=25.0)
        dsp.start_presence_calibration(target_samples=30)

        for sample in [25.0 + 0.02 * math.sin(i) for i in range(30)]:
            dsp.add_sample(sample)

        for sample in [25.0 + 2.0 * math.sin(i / 2.0) for i in range(80)]:
            dsp.add_sample(sample)

        telemetry = dsp.process_telemetry(presence_threshold=0.1, fall_threshold=100.0)

        self.assertTrue(telemetry["calibration"]["ready"])
        self.assertGreater(telemetry["variance"], telemetry["effective_presence_threshold"])
        self.assertTrue(telemetry["presence"])


if __name__ == "__main__":
    unittest.main()
