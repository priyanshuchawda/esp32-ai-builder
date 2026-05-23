import unittest

from backend.csi_motion import MotionLevelEstimator, gate_motion_for_quality


class TestMotionLevelEstimator(unittest.TestCase):
    def test_stable_signal_reports_still(self):
        estimator = MotionLevelEstimator(alpha=0.4)

        result = None
        for _ in range(20):
            result = estimator.update(25.0)

        self.assertEqual(result["level"], "STILL")
        self.assertLess(result["score"], 0.1)

    def test_small_residual_reports_minimal_motion(self):
        estimator = MotionLevelEstimator(alpha=0.5, minimal_threshold=0.2, moderate_threshold=1.0, high_threshold=3.0)
        for _ in range(10):
            estimator.update(25.0)

        result = estimator.update(25.8)

        self.assertEqual(result["level"], "MINIMAL")
        self.assertGreaterEqual(result["score"], 0.2)

    def test_large_residual_reports_high_motion(self):
        estimator = MotionLevelEstimator(alpha=0.6, minimal_threshold=0.2, moderate_threshold=1.0, high_threshold=3.0)
        for _ in range(10):
            estimator.update(25.0)

        result = estimator.update(35.0)

        self.assertEqual(result["level"], "HIGH")
        self.assertGreaterEqual(result["score"], 3.0)

    def test_motion_display_is_unstable_when_signal_quality_is_weak(self):
        motion = {"level": "HIGH", "score": 4.2}
        quality = {"status": "WEAK", "reasons": ["low_fps"]}

        result = gate_motion_for_quality(motion, quality)

        self.assertEqual(result["display_level"], "UNSTABLE")
        self.assertFalse(result["trusted"])
        self.assertIn("low_fps", result["reasons"])


if __name__ == "__main__":
    unittest.main()
