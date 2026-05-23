import unittest
import threading
import time
import random
from unittest.mock import MagicMock
from frontend.app import get_global_resources, RuViewDSP

class TestMultisessionConcurrency(unittest.TestCase):
    def setUp(self):
        self.resources = get_global_resources()
        self.shutdown_event = self.resources["shutdown_event"]
        self.lock = self.resources["lock"]
        self.config = self.resources["config"]
        self.errors = []
        self.read_count = 0
        self.write_count = 0

    def test_concurrent_readers_and_writers(self):
        """
        Simulates multiple dashboard browser tabs (readers) fetching the latest
        telemetry packet under lock, while receiver threads (writers) are
        writing new data packets into the same resource store.
        """
        num_readers = 10
        num_writers = 3
        duration = 0.5  # duration to run the concurrency test

        def reader_worker(reader_id):
            end_time = time.time() + duration
            while time.time() < end_time:
                try:
                    with self.lock:
                        pkg = self.resources["latest_package"]
                        # Verify the packet structure is always intact and valid
                        if pkg is not None:
                            self.assertIn("stats", pkg)
                            self.assertIn("telemetry", pkg)
                            self.assertIn("raw_history", pkg)
                            self.assertIn("filtered_history", pkg)
                            self.assertIn("resp_history", pkg)
                            
                            # Read values to simulate rendering
                            _ = pkg["stats"].get("node_id")
                            _ = pkg["telemetry"].get("presence")
                            _ = len(pkg["raw_history"])
                    self.read_count += 1
                except Exception as e:
                    self.errors.append(f"Reader {reader_id} error: {e}")
                time.sleep(0.001 * random.randint(1, 5))

        def writer_worker(writer_id):
            end_time = time.time() + duration
            seq = 0
            while time.time() < end_time:
                try:
                    # Construct dummy package
                    dummy_pkg = {
                        "stats": {
                            "node_id": f"Node-{writer_id}",
                            "seq": seq,
                            "rssi": -50 + random.randint(-10, 10),
                            "noise": -95,
                            "freq_mhz": 2412,
                            "fps": 50.0
                        },
                        "telemetry": {
                            "presence": True,
                            "breathing_rate": 15 + random.uniform(-2, 2),
                            "heart_rate": 70 + random.uniform(-5, 5),
                            "is_apnea": False,
                            "fall_alert": False,
                            "apnea_status": {"is_apnea": False, "is_hypopnea": False},
                            "apnea_events": []
                        },
                        "raw_history": [random.uniform(10, 40) for _ in range(50)],
                        "filtered_history": [random.uniform(10, 40) for _ in range(50)],
                        "resp_history": [random.uniform(-1, 1) for _ in range(50)]
                    }
                    with self.lock:
                        self.resources["latest_package"] = dummy_pkg
                    seq += 1
                    self.write_count += 1
                except Exception as e:
                    self.errors.append(f"Writer {writer_id} error: {e}")
                time.sleep(0.001 * random.randint(1, 5))

        threads = []
        for i in range(num_readers):
            t = threading.Thread(target=reader_worker, args=(i,))
            threads.append(t)
        for i in range(num_writers):
            t = threading.Thread(target=writer_worker, args=(i,))
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to finish
        for t in threads:
            t.join()

        # Assert no errors occurred during concurrent read/write
        self.assertEqual(len(self.errors), 0, f"Concurrency errors occurred: {self.errors}")
        self.assertGreater(self.read_count, 0, "No reads occurred")
        self.assertGreater(self.write_count, 0, "No writes occurred")

if __name__ == "__main__":
    unittest.main()
