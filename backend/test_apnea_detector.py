import unittest
import time
from frontend.app import ApneaDetector

class TestApneaDetector(unittest.TestCase):
    def test_normal_breathing(self):
        # 1. Normal breathing should not trigger any events
        detector = ApneaDetector(apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10)
        start_ts = time.time()
        
        # Ingest 30 seconds of normal breathing (15 BPM) at 1 Hz
        for i in range(30):
            res = detector.ingest(start_ts + i, br=15.0, presence=True)
            self.assertFalse(res["is_apnea"])
            self.assertFalse(res["is_hypopnea"])
            
        summary = detector.get_event_summary()
        self.assertEqual(summary["total_events"], 0)
        self.assertGreater(summary["baseline_br"], 0.0)

    def test_apnea_event(self):
        # 2. Respiration drop to 0 for 15s should trigger an apnea event
        detector = ApneaDetector(apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10)
        start_ts = time.time()
        
        # 15s of normal breathing to establish baseline
        for i in range(15):
            detector.ingest(start_ts + i, br=15.0, presence=True)
            
        # 15s of flatline/apnea (0.0 BPM)
        for i in range(15, 30):
            res = detector.ingest(start_ts + i, br=0.0, presence=True)
            self.assertTrue(res["is_apnea"])
            self.assertFalse(res["is_hypopnea"])
            
        # Transition back to normal to close the event
        detector.ingest(start_ts + 30, br=15.0, presence=True)
        
        summary = detector.get_event_summary()
        self.assertEqual(summary["total_events"], 1)
        self.assertEqual(summary["apneas"], 1)
        self.assertEqual(summary["hypopneas"], 0)
        self.assertEqual(detector.events[0]["type"], "apnea")
        self.assertEqual(detector.events[0]["duration_sec"], 15.0)

    def test_hypopnea_event(self):
        # 3. Respiration drop by 60% (from 15.0 to 6.0 BPM) for 15s should trigger hypopnea
        detector = ApneaDetector(apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10)
        start_ts = time.time()
        
        # 15s of normal breathing to establish baseline (baseline becomes ~15.0)
        for i in range(15):
            detector.ingest(start_ts + i, br=15.0, presence=True)
            
        # 15s of shallow breathing (6.0 BPM, which is a 60% drop from 15.0 but above apnea_thresh of 3.0)
        for i in range(15, 30):
            res = detector.ingest(start_ts + i, br=6.0, presence=True)
            self.assertFalse(res["is_apnea"])
            self.assertTrue(res["is_hypopnea"])
            
        # Transition back to normal to close the event
        detector.ingest(start_ts + 30, br=15.0, presence=True)
        
        summary = detector.get_event_summary()
        self.assertEqual(summary["total_events"], 1)
        self.assertEqual(summary["apneas"], 0)
        self.assertEqual(summary["hypopneas"], 1)
        self.assertEqual(detector.events[0]["type"], "hypopnea")
        self.assertEqual(detector.events[0]["duration_sec"], 15.0)

    def test_no_presence(self):
        # 4. Absence of human presence should reset active tracking and not trigger events
        detector = ApneaDetector(apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10)
        start_ts = time.time()
        
        # Normal breathing for 10s
        for i in range(10):
            detector.ingest(start_ts + i, br=15.0, presence=True)
            
        # Apnea breathing but presence goes False (e.g. room is empty)
        for i in range(10, 25):
            res = detector.ingest(start_ts + i, br=0.0, presence=False)
            self.assertFalse(res["is_apnea"])
            self.assertFalse(res["is_hypopnea"])
            
        summary = detector.get_event_summary()
        self.assertEqual(summary["total_events"], 0)

    def test_ahi_severity_calculation(self):
        # 5. Verify AHI calculation and severity index mapping
        detector = ApneaDetector(apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10)
        
        # Set start and end times to simulate 1 hour (3600 seconds)
        start_ts = 1700000000.0
        detector.start_time = start_ts
        detector.last_time = start_ts + 3600.0
        
        # Add 6 events
        for i in range(6):
            detector.events.append({
                "type": "apnea",
                "start_ts": start_ts + i * 500,
                "end_ts": start_ts + i * 500 + 15,
                "duration_sec": 15.0,
                "avg_br": 0.0
            })
            
        ahi_info = detector.get_ahi()
        self.assertAlmostEqual(ahi_info["hours"], 1.0, places=4)
        self.assertEqual(ahi_info["events"], 6)
        self.assertAlmostEqual(ahi_info["ahi"], 6.0, places=2)
        # 6 AHI is Mild severity (5 <= AHI < 15)
        self.assertEqual(ahi_info["severity"], "Mild")

if __name__ == "__main__":
    unittest.main()
