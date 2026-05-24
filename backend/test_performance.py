import unittest
import time
import struct
import numpy as np
from frontend.app import (
    parse_adr018_packet,
    RuViewDSP,
    generate_simulated_packet,
)

LIVE_DSP_FPS = 50.0
MAX_DSP_PROCESSING_MS = (1000.0 / LIVE_DSP_FPS) * 0.5

class TestPerformance(unittest.TestCase):
    def setUp(self):
        # Setup dummy binary packet
        magic = 0xC5110001
        node_id = 1
        antennas = 2
        n_subcarriers = 64
        freq_mhz = 2412
        seq = 101
        rssi = -50
        noise = -95
        reserved = 0
        header = struct.pack("<IBBHIIbbH", magic, node_id, antennas, n_subcarriers, freq_mhz, seq, rssi, noise, reserved)
        iq_data = bytes([10, 20] * n_subcarriers)
        self.dummy_packet = header + iq_data
        
        self.dsp = RuViewDSP(fps=50.0)
        # Prepopulate DSP buffer with some samples
        for i in range(100):
            self.dsp.add_sample(25.0 + 2.0 * np.sin(i * 0.1))

    def test_parse_packet_performance(self):
        """Verify that parsing an incoming raw ADR-018 packet executes in under 1 ms."""
        iterations = 500
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            _ = parse_adr018_packet(self.dummy_packet)
            
        elapsed = time.perf_counter() - start_time
        avg_time_ms = (elapsed / iterations) * 1000.0
        
        print(f"\n[PERF] parse_adr018_packet: {avg_time_ms:.4f} ms per packet")
        self.assertLess(avg_time_ms, 1.0, f"Packet parsing is too slow: {avg_time_ms:.4f} ms")

    def test_dsp_processing_performance(self):
        """Keep DSP below half of a 50 Hz frame interval for live-processing headroom."""
        iterations = 300
        start_time = time.perf_counter()
        
        for i in range(iterations):
            self.dsp.add_sample(25.0 + np.sin(i * 0.1))
            _ = self.dsp.process_telemetry(presence_threshold=0.6, fall_threshold=12.0)
            
        elapsed = time.perf_counter() - start_time
        avg_time_ms = (elapsed / iterations) * 1000.0
        
        print(f"\n[PERF] dsp.add_sample + process_telemetry: {avg_time_ms:.4f} ms per sample")
        self.assertLess(
            avg_time_ms,
            MAX_DSP_PROCESSING_MS,
            f"DSP iteration exceeds {MAX_DSP_PROCESSING_MS:.1f} ms live budget: {avg_time_ms:.4f} ms",
        )

    def test_simulator_performance(self):
        """Verify that generating a simulated packet executes in under 1 ms."""
        iterations = 500
        start_time = time.perf_counter()
        
        # Test across different scenarios
        scenarios = ["Fitness", "Normal Sleeping", "Apnea", "Hypopnea", "Fall", "Idle", "Empty Room"]
        for idx in range(iterations):
            scenario = scenarios[idx % len(scenarios)]
            _ = generate_simulated_packet(seq=idx, config_dict={"simulation_mode": scenario})
            
        elapsed = time.perf_counter() - start_time
        avg_time_ms = (elapsed / iterations) * 1000.0
        
        print(f"\n[PERF] generate_simulated_packet: {avg_time_ms:.4f} ms per call")
        self.assertLess(avg_time_ms, 1.0, f"Simulation packet generator is too slow: {avg_time_ms:.4f} ms")

    def test_zero_crossing_scaling(self):
        """Verify that computing zero crossings scales well and executes in under 1 ms for large history buffers."""
        # 500 points represents a large signal history (10 seconds of 50 Hz data)
        large_signal = [float(np.sin(i * 0.1)) for i in range(500)]
        
        iterations = 500
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            _ = self.dsp._compute_bpm_zero_crossing(large_signal)
            
        elapsed = time.perf_counter() - start_time
        avg_time_ms = (elapsed / iterations) * 1000.0
        
        print(f"\n[PERF] _compute_bpm_zero_crossing (500 pts): {avg_time_ms:.4f} ms per check")
        self.assertLess(avg_time_ms, 1.0, f"Zero-crossing computation is too slow: {avg_time_ms:.4f} ms")

if __name__ == "__main__":
    unittest.main()
