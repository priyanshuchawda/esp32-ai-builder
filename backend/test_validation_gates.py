import datetime as dt
import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validation" / "run_quality_gates.py"
SPEC = importlib.util.spec_from_file_location("run_quality_gates", SCRIPT_PATH)
run_quality_gates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_quality_gates)


class TestValidationGates(unittest.TestCase):
    def test_make_run_id_is_compact_and_sortable(self):
        run_id = run_quality_gates.make_run_id(dt.datetime(2026, 5, 23, 13, 18, 10))

        self.assertEqual(run_id, "20260523-131810")

    def test_format_result_matches_compact_gate_output(self):
        result = run_quality_gates.format_result("PASS", "backend pytest", 12.345, Path("x.log"))

        self.assertEqual(result, "PASS | backend pytest | 12.3s | log=x.log")

    def test_slugify_log_names(self):
        self.assertEqual(run_quality_gates.slugify("PlatformIO: pio run"), "platformio--pio-run")


if __name__ == "__main__":
    unittest.main()
