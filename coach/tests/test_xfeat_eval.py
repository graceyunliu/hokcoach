import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from evaluate_xfeat import evaluate


class TestXFeatEvaluation(unittest.TestCase):
    def test_offline_harness_reports_both_matchers(self):
        result = evaluate(scales=(0.75, 1.0), limit=2)

        self.assertFalse(result["real_xfeat_executed"])
        self.assertEqual(len(result["results"]), 2)
        for row in result["results"]:
            self.assertEqual(
                set(row["matchers"]), {"match_template", "xfeat_stub"})
            for metrics in row["matchers"].values():
                self.assertIn("accuracy", metrics)
                self.assertIn("mean_localization_error_px", metrics)


if __name__ == "__main__":
    unittest.main()
