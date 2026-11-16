import csv
import importlib.util
import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "inspector_world", "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

DB_SPEC = importlib.util.spec_from_file_location(
    "inspection_db", os.path.join(TOOLS, "inspection_db.py")
)
inspection_db = importlib.util.module_from_spec(DB_SPEC)
sys.modules["inspection_db"] = inspection_db
DB_SPEC.loader.exec_module(inspection_db)

REPORT_SPEC = importlib.util.spec_from_file_location(
    "inspection_report", os.path.join(TOOLS, "inspection_report.py")
)
inspection_report = importlib.util.module_from_spec(REPORT_SPEC)
REPORT_SPEC.loader.exec_module(inspection_report)


class InspectionReportTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = inspection_db.InspectionDatabase(
            os.path.join(self.temp_dir.name, "inspection.db")
        )
        self.mission_id = inspection_db.create_demo(self.db)
        self.output_dir = os.path.join(self.temp_dir.name, "report")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generates_three_complete_report_files(self):
        paths = inspection_report.generate_report(
            self.db, self.mission_id, self.output_dir
        )

        self.assertEqual(set(paths), {"markdown", "csv", "json"})
        for path in paths.values():
            self.assertTrue(os.path.isfile(path))

        with open(paths["json"], encoding="utf-8") as stream:
            data = json.load(stream)
        self.assertEqual(data["mission"]["status"], "COMPLETED")
        self.assertEqual(len(data["measurements"]), 4)
        self.assertEqual(data["mission"]["metadata"], {"source": "demo"})

        with open(paths["csv"], encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[2]["instrument_code"], "P-02")
        self.assertEqual(rows[2]["status"], "ALARM")

        with open(paths["markdown"], encoding="utf-8") as stream:
            report = stream.read()
        self.assertIn("# Отчёт об инспекции", report)
        self.assertIn("P-02", report)
        self.assertIn("Состояний ALARM: **1**", report)

    def test_rejects_unknown_mission(self):
        with self.assertRaises(ValueError):
            inspection_report.generate_report(self.db, 9999, self.output_dir)


if __name__ == "__main__":
    unittest.main()
