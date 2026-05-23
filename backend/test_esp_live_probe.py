import unittest

from backend.esp_live_probe import (
    SerialProbeResult,
    build_probe_lines,
    summarize_udp,
)


class TestEspLiveProbe(unittest.TestCase):
    def test_udp_summary_fails_when_no_packets_arrive(self):
        summary = summarize_udp(packet_count=0, elapsed_sec=30.0)

        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["reason"], "no_packets")
        self.assertEqual(summary["fps"], 0.0)

    def test_udp_summary_warns_when_packet_rate_is_low(self):
        summary = summarize_udp(packet_count=20, elapsed_sec=10.0, min_fps=5.0)

        self.assertEqual(summary["status"], "WARN")
        self.assertEqual(summary["reason"], "low_fps")
        self.assertEqual(summary["fps"], 2.0)

    def test_udp_summary_passes_when_packet_rate_is_healthy(self):
        summary = summarize_udp(packet_count=120, elapsed_sec=10.0, min_fps=5.0)

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["reason"], "ok")
        self.assertEqual(summary["fps"], 12.0)

    def test_probe_lines_are_compact_and_hide_serial_error_details(self):
        lines = build_probe_lines(
            issue=51,
            duration_sec=30,
            udp_summary={"status": "FAIL", "reason": "no_packets", "packets": 0, "fps": 0.0},
            quality_summary={"status": "BAD", "reasons": ["no_packets"]},
            modes={},
            occupancy={"class": "UNKNOWN", "trusted": False, "reasons": ["signal_quality_bad"]},
            serial_result=SerialProbeResult(
                status="FAIL",
                port="COM5",
                lines=0,
                error_type="PermissionError",
                error_message="could not open port with local device path",
            ),
        )

        self.assertIn("LIVE_PROBE issue=51 status=FAIL duration_sec=30", lines)
        self.assertIn("UDP_STATUS FAIL packets=0 fps=0.0 reason=no_packets", lines)
        self.assertIn("SERIAL_STATUS FAIL port=COM5 lines=0 error=PermissionError", lines)
        self.assertIn("QUALITY_STATUS BAD reasons=no_packets", lines)
        self.assertIn("OCCUPANCY UNKNOWN trusted=False reasons=signal_quality_bad", lines)
        self.assertFalse(any("local device path" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
