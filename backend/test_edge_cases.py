import unittest
import numpy as np
from unittest.mock import MagicMock
from frontend.app import (
    parse_adr018_packet,
    RuViewDSP,
    ApneaDetector,
    BUFFER_SIZE
)

class TestEdgeCases(unittest.TestCase):
    def test_parse_adr018_packet_corrupted_header(self):
        """Test parsing packets with invalid/missing magic or header truncation."""
        # 1. Non-matching magic
        corrupted_magic = bytes([0, 0, 0, 0] + [0]*16 + [10, 20]*64)
        self.assertIsNone(parse_adr018_packet(corrupted_magic))

        # 2. Too short header (e.g., 15 bytes)
        short_packet = bytes([0x01, 0x00, 0x11, 0xC5] + [0]*11)
        self.assertIsNone(parse_adr018_packet(short_packet))

        # 3. Correct magic and header, but missing/truncated subcarrier payload
        # Header specifies 64 subcarriers (needs 64 * 2 = 128 bytes), but we only provide 20 bytes of payload
        header = bytes([0x01, 0x00, 0x11, 0xC5]) + bytes([0]*16) # note: n_subcarriers is at index 6,7 (offset 6)
        # n_subcarriers = 64 (0x0040)
        header_list = list(header)
        header_list[6] = 0x40
        header_list[7] = 0x00
        header = bytes(header_list)
        truncated_packet = header + bytes([1, 2] * 10) # only 20 bytes of subcarriers
        # The parser is lenient and processes whatever subcarrier data is present if header is valid.
        parsed = parse_adr018_packet(truncated_packet)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["node_id"], 0)

    def test_dsp_flat_signal(self):
        """Test DSP filters and metrics with flat signals (constant values)."""
        dsp = RuViewDSP(fps=50.0)
        
        # Inject constant samples
        for _ in range(100):
            dsp.add_sample(25.0)

        # 1. Flat signal should result in zero variance and no presence
        telemetry = dsp.process_telemetry(presence_threshold=0.6, fall_threshold=12.0)
        self.assertFalse(telemetry["presence"])
        self.assertEqual(telemetry["variance"], 0.0)
        self.assertEqual(telemetry["resp_bpm"], 0.0)
        self.assertEqual(telemetry["heart_bpm"], 0.0)

    def test_dsp_negative_and_zero_thresholds(self):
        """Test DSP behavior under zero/negative threshold settings."""
        dsp = RuViewDSP(fps=50.0)
        for _ in range(100):
            dsp.add_sample(25.0)
            
        # If threshold is negative, presence should be True even for flat signals (variance=0.0)
        # (Zero threshold uses strict inequality variance > 0.0, so flat signal returns False)
        telemetry_zero = dsp.process_telemetry(presence_threshold=0.0, fall_threshold=12.0)
        self.assertFalse(telemetry_zero["presence"])

        telemetry_neg = dsp.process_telemetry(presence_threshold=-1.0, fall_threshold=12.0)
        self.assertTrue(telemetry_neg["presence"])
        
        # Fall detection with zero fall threshold should trigger immediately if there's any variation
        dsp2 = RuViewDSP(fps=50.0)
        # Prepopulate with 25 samples to bypass the 30-sample minimum check
        for _ in range(25):
            dsp2.add_sample(25.0)
        # Add values that fluctuate slightly
        for val in [25.0, 26.0, 24.0, 27.0, 23.0]:
            dsp2.add_sample(val)
        telemetry_fall = dsp2.process_telemetry(presence_threshold=0.6, fall_threshold=0.0)
        self.assertTrue(telemetry_fall["fall_alert"])

    def test_dsp_high_frequency_noise(self):
        """Test DSP filters are stable and suppress high-frequency noise outside breathing bands."""
        dsp = RuViewDSP(fps=50.0)
        # Create a low-frequency respiration wave (e.g., 0.2 Hz, which is 12 BPM)
        # mixed with a strong high-frequency noise component (20 Hz)
        t = np.linspace(0, 4.0, 200) # 200 samples at 50 Hz
        respiration_component = 2.0 * np.sin(2 * np.pi * 0.2 * t)
        noise_component = 5.0 * np.sin(2 * np.pi * 20.0 * t)
        signal = 25.0 + respiration_component + noise_component
        
        for sample in signal:
            dsp.add_sample(sample)
            
        telemetry = dsp.process_telemetry(presence_threshold=0.1, fall_threshold=100.0)
        
        # Presence should be True due to raw variance
        self.assertTrue(telemetry["presence"])
        
        # The respiration rate should detect the low-frequency component (12 BPM +/- 3 BPM)
        # instead of being dominated by the 20 Hz (which would be 240+ BPM)
        self.assertLess(telemetry["resp_bpm"], 30.0)
        self.assertGreater(telemetry["resp_bpm"], 5.0)

    def test_apnea_detector_edge_cases(self):
        """Test apnea detector state transitions and duration calculations under edge cases."""
        detector = ApneaDetector(apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10)
        
        # 1. No presence: should reset event and return false
        res = detector.ingest(timestamp=100.0, br=15.0, presence=False)
        self.assertFalse(res["is_apnea"])
        self.assertFalse(res["is_hypopnea"])
        self.assertIsNone(detector.current_event)

        # 2. Ingest normal breathing rate to build baseline
        # Baseline needs br > 2 * apnea_thresh (br > 6.0)
        for ts in range(100, 150):
            detector.ingest(timestamp=float(ts), br=16.0, presence=True)
        self.assertIsNotNone(detector.baseline_br)
        self.assertAlmostEqual(detector.baseline_br, 16.0, delta=1.0)

        # 3. Enter hypopnea (BR drops below 50% baseline, but above apnea thresh, e.g. 7.0)
        res = detector.ingest(timestamp=150.0, br=7.0, presence=True)
        self.assertTrue(res["is_hypopnea"])
        self.assertFalse(res["is_apnea"])
        self.assertEqual(detector.current_event["type"], "hypopnea")

        # 4. Upgrade hypopnea to apnea (BR drops below apnea thresh, e.g. 2.0)
        res = detector.ingest(timestamp=151.0, br=2.0, presence=True)
        self.assertTrue(res["is_apnea"])
        self.assertEqual(detector.current_event["type"], "apnea")

        # 5. Hold apnea for 12 seconds to cross minimum duration of 10s
        for ts in range(152, 165):
            detector.ingest(timestamp=float(ts), br=2.0, presence=True)
            
        # 6. End event with normal breathing
        res = detector.ingest(timestamp=165.0, br=16.0, presence=True)
        self.assertFalse(res["is_apnea"])
        self.assertIsNone(detector.current_event)
        self.assertEqual(len(detector.events), 1)
        self.assertEqual(detector.events[0]["type"], "apnea")
        self.assertEqual(detector.events[0]["duration_sec"], 15.0)

if __name__ == "__main__":
    unittest.main()
