import unittest

from backend.csi_fingerprint import build_fingerprint, format_fingerprint_lines


class TestCsiFingerprint(unittest.TestCase):
    def test_builds_compact_fingerprint_from_amplitudes(self):
        fingerprint = build_fingerprint([10, 12, 18, 26, 25, 15], bins=6)

        self.assertEqual(fingerprint["bins"], 6)
        self.assertEqual(fingerprint["min"], 10.0)
        self.assertEqual(fingerprint["max"], 26.0)
        self.assertEqual(fingerprint["spread"], 16.0)
        self.assertEqual(len(fingerprint["bars"]), 6)
        self.assertTrue(fingerprint["bars"].isascii())

    def test_formats_fingerprint_lines(self):
        fingerprint = build_fingerprint([10, 12, 18, 26, 25, 15], bins=6)

        lines = format_fingerprint_lines(fingerprint, prefix="SIM_FINGERPRINT")

        self.assertEqual(lines[0], "SIM_FINGERPRINT bins=6 mean=17.67 spread=16.0")
        self.assertTrue(lines[1].startswith("SIM_FINGERPRINT bars="))

    def test_empty_input_is_safe(self):
        fingerprint = build_fingerprint([])

        self.assertEqual(fingerprint["bins"], 0)
        self.assertEqual(fingerprint["bars"], "")


if __name__ == "__main__":
    unittest.main()
