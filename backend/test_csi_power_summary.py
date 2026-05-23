import unittest

from backend.csi_power_summary import build_power_summary, format_power_summary_lines


class TestCsiPowerSummary(unittest.TestCase):
    def test_summarizes_occupied_breathing_and_heart_signal(self):
        summary = build_power_summary(
            telemetry={
                "presence": True,
                "resp_bpm": 14.8,
                "heart_bpm": 72.2,
                "fall_detected": False,
                "motion": {"display_level": "STILL", "score": 0.12, "trusted": True},
                "occupancy": {"class": "OCCUPIED", "trusted": True, "reasons": []},
            },
            signal_quality={"status": "GOOD", "fps": 24.8, "reasons": []},
        )

        self.assertEqual(summary["headline"], "Human presence visible through Wi-Fi CSI")
        self.assertIn("presence", summary["capabilities"])
        self.assertIn("breathing", summary["capabilities"])
        self.assertIn("heart_rate", summary["capabilities"])
        self.assertEqual(summary["demo_state"], "OCCUPIED_STILL")
        self.assertEqual(summary["confidence"], "HIGH")

    def test_summarizes_fall_as_critical_event(self):
        summary = build_power_summary(
            telemetry={
                "presence": True,
                "resp_bpm": 0,
                "heart_bpm": 0,
                "fall_detected": True,
                "motion": {"display_level": "HIGH", "score": 9.5, "trusted": True},
                "occupancy": {"class": "OCCUPIED", "trusted": True, "reasons": []},
            },
            signal_quality={"status": "GOOD", "fps": 20.0, "reasons": []},
        )

        self.assertEqual(summary["demo_state"], "FALL_EVENT")
        self.assertEqual(summary["headline"], "Fall-like motion spike detected")
        self.assertIn("fall_alert", summary["capabilities"])
        self.assertEqual(summary["confidence"], "HIGH")

    def test_marks_weak_signal_as_watch_mode(self):
        summary = build_power_summary(
            telemetry={
                "presence": True,
                "resp_bpm": 0,
                "heart_bpm": 0,
                "fall_detected": False,
                "motion": {"display_level": "UNSTABLE", "score": 2.1, "trusted": False},
                "occupancy": {"class": "UNKNOWN", "trusted": False, "reasons": ["signal_quality_weak_blocked"]},
            },
            signal_quality={"status": "WEAK", "fps": 2.7, "reasons": ["low_fps", "rssi_unstable"]},
        )

        self.assertEqual(summary["demo_state"], "SIGNAL_WATCH")
        self.assertEqual(summary["confidence"], "LOW")
        self.assertIn("improve_wifi_signal_or_reduce_receiver_load", summary["next_actions"])

    def test_formats_compact_terminal_lines(self):
        summary = {
            "demo_state": "OCCUPIED_STILL",
            "headline": "Human presence visible through Wi-Fi CSI",
            "confidence": "HIGH",
            "capabilities": ["presence", "breathing"],
            "next_actions": [],
        }

        lines = format_power_summary_lines(summary, prefix="SIM_DEMO")

        self.assertEqual(lines[0], "SIM_DEMO state=OCCUPIED_STILL confidence=HIGH")
        self.assertIn("SIM_DEMO headline=Human presence visible through Wi-Fi CSI", lines)
        self.assertIn("SIM_DEMO capabilities=presence,breathing", lines)


if __name__ == "__main__":
    unittest.main()
