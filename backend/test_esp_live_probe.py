import unittest

from backend.esp_live_probe import (
    SerialProbeResult,
    build_probe_lines,
    load_firmware_network_config,
    summarize_target_ip,
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
            config_summary=None,
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

    def test_load_firmware_network_config_ignores_secret_values(self):
        text = '\n'.join(
            [
                '#define WIFI_SSID "room-wifi"',
                '#define WIFI_PASSWORD "super-secret"',
                '#define TARGET_IP "192.168.29.10"',
                '#define TARGET_PORT 5005',
            ]
        )

        config = load_firmware_network_config(text=text)

        self.assertEqual(config, {"target_ip": "192.168.29.10", "target_port": 5005})

    def test_target_ip_summary_fails_on_mismatch(self):
        summary = summarize_target_ip(target_ip="192.168.29.10", local_ip="192.168.29.20")

        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["reason"], "target_ip_mismatch")

    def test_probe_lines_include_config_status(self):
        lines = build_probe_lines(
            issue=53,
            duration_sec=5,
            config_summary={
                "status": "FAIL",
                "reason": "target_ip_mismatch",
                "target_ip": "192.168.29.10",
                "local_ip": "192.168.29.20",
                "target_port": 5005,
            },
            udp_summary={"status": "FAIL", "reason": "no_packets", "packets": 0, "fps": 0.0},
            quality_summary={"status": "BAD", "reasons": ["no_packets"]},
            modes={},
            occupancy={"class": "UNKNOWN", "trusted": False, "reasons": ["signal_quality_bad"]},
        )

        self.assertIn("LIVE_PROBE issue=53 status=FAIL duration_sec=5", lines)
        self.assertIn(
            "CONFIG_STATUS FAIL target_ip=192.168.29.10 local_ip=192.168.29.20 target_port=5005 reason=target_ip_mismatch",
            lines,
        )

    def test_config_mismatch_controls_overall_probe_status(self):
        lines = build_probe_lines(
            issue=53,
            duration_sec=5,
            config_summary={
                "status": "FAIL",
                "reason": "target_ip_mismatch",
                "target_ip": "192.168.29.10",
                "local_ip": "192.168.29.20",
                "target_port": 5005,
            },
            udp_summary={"status": "PASS", "reason": "ok", "packets": 100, "fps": 20.0},
            quality_summary={"status": "GOOD", "reasons": []},
            modes={128: 100},
            occupancy={"class": "EMPTY", "trusted": True, "reasons": []},
        )

        self.assertIn("LIVE_PROBE issue=53 status=FAIL duration_sec=5", lines)


if __name__ == "__main__":
    unittest.main()
