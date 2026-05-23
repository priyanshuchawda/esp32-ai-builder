import unittest
import time as py_time
import numpy as np
from frontend.app import generate_simulated_packet, RuViewDSP

class TestSignalSimulation(unittest.TestCase):
    def test_simulator_scenarios(self):
        modes = ["Fitness", "Normal Sleeping", "Apnea", "Hypopnea", "Fall", "Idle", "Empty Room"]
        
        for mode in modes:
            config = {"simulation_mode": mode}
            packet = generate_simulated_packet(seq=1, config_dict=config)
            
            self.assertIsNotNone(packet)
            self.assertEqual(packet["seq"], 1)
            self.assertGreater(packet["freq_mhz"], 2400)
            self.assertEqual(packet["n_subcarriers"], 128)
            
            if mode == "Empty Room":
                self.assertAlmostEqual(packet["raw_signal"], 25.0, delta=0.5)
                
    def test_dsp_pipeline(self):
        dsp = RuViewDSP(fps=25.0)
        config = {"simulation_mode": "Fitness"}
        
        # Mock time.time to advance by 0.04 seconds per call
        start_t = 1700000000.0
        current_calls = 0
        
        def mock_time():
            nonlocal current_calls
            # Since generate_simulated_packet calls time.time() twice (once for now_ms, once for t),
            # we increment time by 0.04s every two calls
            t_val = start_t + (current_calls // 2) * 0.04
            current_calls += 1
            return t_val
            
        original_time = py_time.time
        py_time.time = mock_time
        
        try:
            # Inject 100 packets (4 seconds of simulated data at 25 Hz)
            for seq in range(100):
                packet = generate_simulated_packet(seq=seq, config_dict=config)
                dsp.add_sample(packet["raw_signal"])
                
            telemetry = dsp.process_telemetry(presence_threshold=0.6, fall_threshold=12.0)
        finally:
            py_time.time = original_time
        
        self.assertTrue(telemetry["presence"])
        self.assertGreater(telemetry["variance"], 0.6)
        self.assertIn("resp_bpm", telemetry)
        self.assertIn("heart_bpm", telemetry)
        self.assertIn("fall_alert", telemetry)

if __name__ == "__main__":
    unittest.main()
