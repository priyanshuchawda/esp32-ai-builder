import unittest

from backend.csi_quality import SignalQualityMonitor


class TestSignalQualityMonitor(unittest.TestCase):
    def test_good_quality_for_contiguous_stable_packets(self):
        monitor = SignalQualityMonitor(window_seconds=10.0)

        for i in range(30):
            monitor.record_packet(seq=i, rssi=-45 + (i % 2), n_subcarriers=128, timestamp=100.0 + (i * 0.1))

        summary = monitor.summary(now=103.1)

        self.assertEqual(summary["status"], "GOOD")
        self.assertGreaterEqual(summary["fps"], 8.0)
        self.assertEqual(summary["sequence_gaps"], 0)
        self.assertEqual(summary["subcarrier_modes"], {128: 30})
        self.assertEqual(summary["reasons"], [])

    def test_weak_quality_for_low_packet_rate(self):
        monitor = SignalQualityMonitor(window_seconds=10.0)

        for i in range(6):
            monitor.record_packet(seq=i, rssi=-60, n_subcarriers=128, timestamp=100.0 + i)

        summary = monitor.summary(now=106.0)

        self.assertEqual(summary["status"], "WEAK")
        self.assertIn("low_fps", summary["reasons"])
        self.assertLess(summary["fps"], 5.0)

    def test_bad_quality_when_stream_is_stale(self):
        monitor = SignalQualityMonitor(window_seconds=10.0, stale_seconds=3.0)
        monitor.record_packet(seq=1, rssi=-50, n_subcarriers=128, timestamp=100.0)

        summary = monitor.summary(now=105.0)

        self.assertEqual(summary["status"], "BAD")
        self.assertIn("stale_stream", summary["reasons"])

    def test_sequence_gaps_and_rssi_spread_are_reported(self):
        monitor = SignalQualityMonitor(window_seconds=10.0)

        samples = [
            (1, -35, 128, 100.0),
            (2, -80, 128, 100.1),
            (8, -78, 192, 100.2),
            (9, -38, 192, 100.3),
            (10, -40, 64, 100.4),
        ]
        for seq, rssi, n_sub, ts in samples:
            monitor.record_packet(seq=seq, rssi=rssi, n_subcarriers=n_sub, timestamp=ts)

        summary = monitor.summary(now=100.5)

        self.assertEqual(summary["sequence_gaps"], 1)
        self.assertGreater(summary["rssi_spread"], 30)
        self.assertIn("sequence_gaps", summary["reasons"])
        self.assertIn("rssi_unstable", summary["reasons"])
        self.assertIn("mixed_subcarriers", summary["reasons"])

    def test_rare_subcarrier_mode_changes_do_not_mark_stream_mixed(self):
        monitor = SignalQualityMonitor(window_seconds=10.0)

        for i in range(95):
            monitor.record_packet(seq=i, rssi=-50, n_subcarriers=192, timestamp=100.0 + (i * 0.05))
        for i in range(95, 100):
            monitor.record_packet(seq=i, rssi=-50, n_subcarriers=128, timestamp=100.0 + (i * 0.05))

        summary = monitor.summary(now=105.0)

        self.assertNotIn("mixed_subcarriers", summary["reasons"])
        self.assertEqual(summary["dominant_subcarriers"], 192)
        self.assertAlmostEqual(summary["dominant_subcarrier_ratio"], 0.95)


if __name__ == "__main__":
    unittest.main()
