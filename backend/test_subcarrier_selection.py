import unittest

from backend.csi_subcarriers import SubcarrierSelector, normalize_amplitudes


class TestSubcarrierSelection(unittest.TestCase):
    def test_normalize_amplitudes_pads_and_truncates_to_target_length(self):
        self.assertEqual(normalize_amplitudes([1.0, 2.0], target_len=4), [1.0, 2.0, 0.0, 0.0])
        self.assertEqual(normalize_amplitudes([1.0, 2.0, 3.0], target_len=2), [1.0, 2.0])

    def test_selector_prefers_stable_populated_subcarriers_over_noisy_bins(self):
        selector = SubcarrierSelector(target_len=4, top_k=2, min_frames=4)
        frames = [
            [10.0, 20.0, 30.0, 40.0],
            [10.2, 25.0, 30.1, 80.0],
            [9.9, 10.0, 29.9, 5.0],
            [10.1, 40.0, 30.0, 70.0],
        ]

        for frame in frames:
            result = selector.add_frame(frame)

        self.assertEqual(result["selected_indices"], [2, 0])
        self.assertAlmostEqual(result["selected_signal"], (10.1 + 30.0) / 2, places=4)
        self.assertEqual(result["frame_count"], 4)

    def test_selector_falls_back_to_full_mean_until_enough_frames_arrive(self):
        selector = SubcarrierSelector(target_len=4, top_k=2, min_frames=3)

        result = selector.add_frame([10.0, 20.0])

        self.assertEqual(result["selected_indices"], [])
        self.assertAlmostEqual(result["selected_signal"], 15.0, places=4)
        self.assertEqual(result["normalized_amplitudes"], [10.0, 20.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
