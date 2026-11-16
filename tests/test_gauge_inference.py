import importlib.util
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(ROOT, "inspector_world", "tools", "gauge_inference.py")
SPEC = importlib.util.spec_from_file_location("gauge_inference", MODULE_PATH)
gauge_inference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gauge_inference)


class GaugeInferenceRulesTest(unittest.TestCase):
    def test_normalized_values_are_converted_to_instrument_units(self):
        self.assertAlmostEqual(
            gauge_inference.normalized_to_value("P-01", 0.5), 0.8
        )
        self.assertAlmostEqual(
            gauge_inference.normalized_to_value("T-01", 0.5), 60.0
        )
        self.assertAlmostEqual(
            gauge_inference.normalized_to_value("V-01", 0.5), -0.05
        )

    def test_status_uses_each_instruments_safe_range(self):
        self.assertEqual(gauge_inference.value_status("P-01", 0.62), "OK")
        self.assertEqual(gauge_inference.value_status("P-02", 7.8), "ALARM")
        self.assertEqual(gauge_inference.value_status("V-01", -0.05), "OK")


if __name__ == "__main__":
    unittest.main()
