import unittest
import numpy as np
import time
import frontend.app as app
from frontend.app import RuViewDSP

class TestDSPDetails(unittest.TestCase):
    def test_zero_crossing_bpm_calculation(self):
        dsp = RuViewDSP(fps=25.0)
        
        # Test Case 1: Analytical Sine Wave representing 12 BPM Respiration
        # 12 BPM = 0.2 Hz frequency. At 25 Hz sampling, period = 125 samples.
        fps = 25.0
        duration = 8.0  # 8 seconds = 200 samples
        t = np.arange(0, duration, 1.0 / fps)
        
        # Respiration wave (0.2 Hz)
        resp_freq = 0.2
        signal_resp = np.sin(2 * np.pi * resp_freq * t)
        
        # Check crossings count:
        # Frequency = 0.2 Hz, duration = 8.0s -> 0.2 * 8.0 = 1.6 cycles.
        # Zero crossings = cycles * 2 = 3.2 crossings. We should see about 3 or 4 crossings.
        # Formula: crossings / 2 / duration * 60 = cycles / duration * 60 = freq * 60 = 0.2 * 60 = 12.0 BPM.
        bpm_resp = dsp._compute_bpm_zero_crossing(signal_resp)
        # We expect around 12 BPM, let's check if it is within reasonable range (11.0 to 13.0)
        self.assertAlmostEqual(bpm_resp, 12.0, delta=2.0)

        # Test Case 2: Analytical Sine Wave representing 75 BPM Heart Rate
        # 75 BPM = 1.25 Hz frequency
        heart_freq = 1.25
        signal_heart = np.sin(2 * np.pi * heart_freq * t)
        bpm_heart = dsp._compute_bpm_zero_crossing(signal_heart)
        self.assertAlmostEqual(bpm_heart, 75.0, delta=5.0)

    def test_fall_detection_trigger(self):
        dsp = RuViewDSP(fps=25.0)
        
        # Fill filtered history with stable baseline values
        for _ in range(50):
            dsp.filtered_history.append(25.0)
            
        # Check that there is no fall alert initially
        telemetry = dsp.process_telemetry(presence_threshold=0.6, fall_threshold=10.0)
        self.assertFalse(telemetry["fall_alert"])
        
        # Inject a sudden acceleration spike (e.g. 25 -> 35 -> 10 -> 25)
        # This will create a large second derivative (deceleration/acceleration spike)
        # diff(25, 25, 35, 10, 25) -> d1 = (0, 10, -25, 15) -> d2 = (10, -35, 40) -> max absolute is 40.
        dsp.filtered_history.append(25.0)
        dsp.filtered_history.append(35.0)
        dsp.filtered_history.append(10.0)
        dsp.filtered_history.append(25.0)
        
        telemetry = dsp.process_telemetry(presence_threshold=0.6, fall_threshold=10.0)
        self.assertTrue(telemetry["fall_alert"])
        self.assertGreater(telemetry["acceleration"], 10.0)

    def test_rep_counter_hysteresis(self):
        dsp = RuViewDSP(fps=25.0)
        
        # We simulate 3 full squat cycles
        # Squat is a large movement. We fill filtered_history with 120 samples (approx 5 seconds)
        # representing a sine wave of amplitude 1.5. Standard deviation will be > 0.4.
        fps = 25.0
        t = np.arange(0, 10, 1.0 / fps)
        # 3 cycles in 10 seconds (freq = 0.3 Hz)
        squat_signal = 25.0 + 1.5 * np.sin(2 * np.pi * 0.3 * t)
        
        # Mock time.time to advance by 0.04 seconds per step
        start_t = 1700000000.0
        current_calls = 0
        
        def mock_time():
            nonlocal current_calls
            t_val = start_t + current_calls * 0.04
            current_calls += 1
            return t_val
            
        import time as py_time
        original_time = py_time.time
        py_time.time = mock_time
        
        try:
            # We need presence to be active. Variance of raw signal must be > presence_threshold.
            # We will populate raw_history with corresponding values
            for val in squat_signal:
                dsp.raw_history.append(val)
                dsp.filtered_history.append(val)
                # Process telemetry at each sample to simulate real time rep counting
                telemetry = dsp.process_telemetry(presence_threshold=0.6, fall_threshold=20.0)
        finally:
            py_time.time = original_time
            
        # The rep counter triggers on transition from state 1 (up) to 0 (down)
        # We expect around 2 to 3 reps counted
        self.assertGreaterEqual(telemetry["rep_count"], 2)
        self.assertLessEqual(telemetry["rep_count"], 4)

    def test_bandpass_filter_fallback(self):
        dsp = RuViewDSP(fps=25.0)
        data = list(np.random.normal(25.0, 0.5, 50))
        
        # Test scipy path (if scipy is available)
        if app.HAS_SCIPY:
            val_scipy = dsp._bandpass_filter(data, 0.1, 0.5)
            self.assertIsInstance(val_scipy, float)
            
        # Force fallback path by mocking HAS_SCIPY to False
        app.HAS_SCIPY = False
        try:
            val_fallback = dsp._bandpass_filter(data, 0.1, 0.5)
            self.assertIsInstance(val_fallback, float)
        finally:
            # Restore SciPy flag
            app.HAS_SCIPY = 'scipy' in globals() or any('scipy' in str(m) for m in globals().values())
            # Let's verify manually using imported scipy status
            from scipy.signal import butter
            app.HAS_SCIPY = True

    def test_add_sample_filters_large_spikes_before_presence_history(self):
        dsp = RuViewDSP(fps=25.0)

        for _ in range(9):
            dsp.add_sample(25.0)
        dsp.add_sample(90.0)

        self.assertEqual(dsp.raw_history[-1], 25.0)
        self.assertEqual(dsp.spike_filter.replaced_count, 1)

if __name__ == "__main__":
    unittest.main()
