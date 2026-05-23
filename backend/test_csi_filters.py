import unittest

from backend.csi_filters import StreamingHampelFilter


class TestStreamingHampelFilter(unittest.TestCase):
    def test_replaces_single_large_spike_with_local_median(self):
        filt = StreamingHampelFilter(window_size=5, threshold=3.0, min_spike_delta=5.0)
        values = [25.0, 25.2, 24.9, 25.1, 25.0, 82.0]

        outputs = [filt.update(value) for value in values]

        self.assertAlmostEqual(outputs[-1], 25.0, places=2)
        self.assertEqual(filt.replaced_count, 1)

    def test_allows_small_changes_inside_spike_delta(self):
        filt = StreamingHampelFilter(window_size=5, threshold=3.0, min_spike_delta=5.0)
        values = [25.0, 25.1, 24.9, 25.2, 25.0, 28.0]

        outputs = [filt.update(value) for value in values]

        self.assertEqual(outputs[-1], 28.0)
        self.assertEqual(filt.replaced_count, 0)

    def test_warms_up_without_replacing(self):
        filt = StreamingHampelFilter(window_size=5, threshold=3.0, min_spike_delta=5.0)

        self.assertEqual(filt.update(100.0), 100.0)
        self.assertEqual(filt.replaced_count, 0)


if __name__ == "__main__":
    unittest.main()
