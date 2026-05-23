import unittest

from backend.csi_demo_simulator import build_demo_snapshot, format_demo_snapshot


class TestCsiDemoSimulator(unittest.TestCase):
    def test_occupied_still_snapshot_highlights_presence_vitals(self):
        snapshot = build_demo_snapshot("occupied_still")

        self.assertEqual(snapshot["scenario"], "occupied_still")
        self.assertEqual(snapshot["summary"]["demo_state"], "OCCUPIED_STILL")
        self.assertIn("breathing", snapshot["summary"]["capabilities"])
        self.assertIn("heart_rate", snapshot["summary"]["capabilities"])

    def test_fall_snapshot_highlights_critical_event(self):
        snapshot = build_demo_snapshot("fall_event")

        self.assertEqual(snapshot["summary"]["demo_state"], "FALL_EVENT")
        self.assertIn("fall_alert", snapshot["summary"]["capabilities"])

    def test_formats_snapshot_as_terminal_showcase(self):
        lines = format_demo_snapshot(build_demo_snapshot("walking"))

        self.assertIn("DEMO_SCENARIO walking", lines)
        self.assertIn("SIM_DEMO state=OCCUPIED_MOVING confidence=HIGH", lines)
        self.assertTrue(any(line.startswith("SIM_FINGERPRINT bars=") for line in lines))
        self.assertTrue(any(line.startswith("SIM_METRIC") for line in lines))


if __name__ == "__main__":
    unittest.main()
