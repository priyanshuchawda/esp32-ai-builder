import unittest
from frontend.app import (
    draw_vital_signs,
    draw_sleep_apnea,
    draw_wifi_signal,
    draw_presence,
    draw_apnea_events,
    draw_indicators_and_keys
)

class MockStreamlitContainer:
    def __init__(self):
        self.markdown_calls = []
        self.empty_calls = 0

    def markdown(self, body, unsafe_allow_html=False):
        self.markdown_calls.append((body, unsafe_allow_html))

    def empty(self):
        self.empty_calls += 1


class TestDashboardIntegrity(unittest.TestCase):
    def test_draw_vital_signs_absent(self):
        container = MockStreamlitContainer()
        telemetry = {
            "heart_bpm": 80.0,
            "resp_bpm": 18.0,
            "presence": False,
            "variance": 0.05
        }
        draw_vital_signs(telemetry, container)
        self.assertEqual(len(container.markdown_calls), 1)
        html = container.markdown_calls[0][0]
        # When absent, heart rate and respiration should show "---"
        self.assertIn("---", html)
        self.assertIn("HEART RATE", html)
        self.assertIn("RESPIRATION", html)

    def test_draw_vital_signs_present(self):
        container = MockStreamlitContainer()
        telemetry = {
            "heart_bpm": 75.0,
            "resp_bpm": 14.0,
            "presence": True,
            "variance": 1.2
        }
        draw_vital_signs(telemetry, container)
        self.assertEqual(len(container.markdown_calls), 1)
        html = container.markdown_calls[0][0]
        # Should display values
        self.assertIn("75", html)
        self.assertIn("14", html)
        # Confidence should be a percentage, not 0
        self.assertNotIn("0%</span>", html)

    def test_draw_sleep_apnea_states(self):
        # Case 1: Absent
        container = MockStreamlitContainer()
        telemetry = {
            "presence": False,
            "apnea_status": {
                "is_apnea": False,
                "is_hypopnea": False,
                "current_event_duration": 0.0,
                "baseline_br": 15.0,
                "ahi": 4.2,
                "severity": "Normal",
                "hours": 0.5,
                "summary": {"total_events": 2, "apneas": 1, "hypopneas": 1}
            }
        }
        draw_sleep_apnea(telemetry, container)
        self.assertIn("[-]", container.markdown_calls[0][0])
        
        # Case 2: Active Apnea
        container = MockStreamlitContainer()
        telemetry["presence"] = True
        telemetry["apnea_status"]["is_apnea"] = True
        telemetry["apnea_status"]["current_event_duration"] = 15.2
        draw_sleep_apnea(telemetry, container)
        self.assertIn("⚠️ APNEA DETECTED", container.markdown_calls[0][0])
        self.assertIn("15s", container.markdown_calls[0][0])
        self.assertIn("Normal", container.markdown_calls[0][0]) # Severity value

    def test_draw_wifi_signal(self):
        container = MockStreamlitContainer()
        stats = {
            "rssi": -45,
            "noise": -96
        }
        telemetry = {
            "presence": True,
            "variance": 1.45
        }
        raw_hist = [24.5, 25.1, 24.8, 25.4, 25.0]
        draw_wifi_signal(stats, telemetry, raw_hist, container)
        html = container.markdown_calls[0][0]
        self.assertIn("-45 dBm", html)
        self.assertIn("1.45", html)
        self.assertIn("svg", html)

    def test_draw_presence_badge(self):
        # Present
        container_p = MockStreamlitContainer()
        draw_presence({"presence": True}, container_p)
        self.assertIn("PRESENT", container_p.markdown_calls[0][0])

        # Absent
        container_a = MockStreamlitContainer()
        draw_presence({"presence": False}, container_a)
        self.assertIn("ABSENT", container_a.markdown_calls[0][0])

    def test_draw_apnea_events(self):
        container = MockStreamlitContainer()
        telemetry = {
            "apnea_status": {
                "events": [
                    {"type": "apnea", "start_ts": 1700000000.0, "end_ts": 1700000015.0, "duration_sec": 15.0, "avg_br": 0.0},
                    {"type": "hypopnea", "start_ts": 1700001000.0, "end_ts": 1700001020.0, "duration_sec": 20.0, "avg_br": 6.5}
                ]
            }
        }
        draw_apnea_events(telemetry, container)
        html = container.markdown_calls[0][0]
        self.assertIn("APNEA", html)
        self.assertIn("HYPOPNEA", html)
        self.assertIn("Dur: 15.0s", html)
        self.assertIn("Dur: 20.0s", html)

    def test_draw_indicators_and_keys(self):
        # Idle/sleeping (presence=True, variance=0.2) -> Gesture active
        container = MockStreamlitContainer()
        telemetry = {
            "presence": True,
            "variance": 0.2,
            "apnea_status": {"is_apnea": False, "is_hypopnea": False}
        }
        draw_indicators_and_keys(telemetry, container)
        html = container.markdown_calls[0][0]
        self.assertIn("GESTURE", html)
        self.assertIn("GAIT", html)

if __name__ == "__main__":
    unittest.main()
