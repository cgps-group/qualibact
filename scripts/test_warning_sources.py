"""Regression checks for native warning thresholds and legacy missing data."""
import tempfile
import unittest
from pathlib import Path

from build_manifests import build_manifest, read_summary_csv


class WarningSources(unittest.TestCase):
    def manifest(self, summary, native=None, source="computed"):
        return build_manifest(
            "Regression_species", "regression", {"genome_count": 1000},
            {"Genome_Size": summary}, [], "test",
            metrics_csv_bounds={"Genome_Size": {
                "final_lower": 1800000, "final_upper": 2300000,
                "warn_lower": (native or {}).get("lower"),
                "warn_upper": (native or {}).get("upper"), "source": source,
            }},
        )["thresholds"][0]

    def test_failure_bounds_are_not_used_as_warnings(self):
        row = self.manifest({"ml_lower": 2033458.67, "ml_upper": 2397461})
        self.assertIsNone(row["warn_lower"])
        self.assertIsNone(row["warn_upper"])
        self.assertEqual(row["final_upper"], 2300000)

    def test_real_summary_warning_columns_are_the_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "summary.csv").write_text(
                "metric,FINAL_LOWER,FINAL_UPPER,WARN_LOWER,WARN_UPPER\n"
                "Genome_Size,1950123,2397461,2000000,2300000\n"
            )
            summary = read_summary_csv(Path(folder))["Genome_Size"]
        row = self.manifest(summary)
        self.assertEqual((row["warn_lower"], row["warn_upper"]), (2000000, 2300000))

    def test_native_warnings_take_precedence(self):
        row = self.manifest(
            {"warn_lower": 2000000, "warn_upper": 2300000},
            {"lower": 2050000, "upper": 2250000},
        )
        self.assertEqual((row["warn_lower"], row["warn_upper"]), (2050000, 2250000))

    def test_external_criteria_do_not_gain_warning_bands(self):
        row = self.manifest(
            {"warn_lower": 2000000, "warn_upper": 2300000}, source="external",
        )
        self.assertIsNone(row["warn_lower"])
        self.assertIsNone(row["warn_upper"])

    def test_blank_native_warning_cells_are_not_backfilled(self):
        row = build_manifest(
            "Regression_species", "regression", {"genome_count": 1000},
            {"N50": {"warn_lower": 23000, "warn_upper": 71562}}, [], "test",
            metrics_csv_bounds={"N50": {
                "final_lower": 19000, "final_upper": None,
                "warn_lower": 23000, "warn_upper": None,
                "source": "computed", "native_warning_columns": True,
            }},
        )["thresholds"]
        n50 = next(r for r in row if r["metric"] == "N50")
        self.assertEqual(n50["warn_lower"], 23000)
        self.assertIsNone(n50["warn_upper"])


if __name__ == "__main__":
    unittest.main()
