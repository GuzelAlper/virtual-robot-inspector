import importlib.util
import os
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(ROOT, "inspector_world", "tools", "inspection_db.py")
SPEC = importlib.util.spec_from_file_location("inspection_db", MODULE_PATH)
inspection_db = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspection_db)


class InspectionDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "inspection.db")
        self.db = inspection_db.InspectionDatabase(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_and_complete_mission(self):
        mission_id = inspection_db.create_demo(self.db)
        summary = self.db.mission_summary(mission_id)

        self.assertEqual(summary["mission"]["status"], "COMPLETED")
        self.assertEqual(summary["mission"]["returned_to_start"], 1)
        self.assertEqual(len(summary["measurements"]), 4)
        self.assertEqual(
            [row["instrument_code"] for row in summary["measurements"]],
            ["P-01", "T-01", "P-02", "V-01"],
        )
        self.assertEqual(summary["measurements"][2]["status"], "ALARM")
        self.assertEqual(len(summary["events"]), 1)

    def test_rejects_invalid_confidence(self):
        mission_id = self.db.start_mission("test_scene")
        station_id = self.db.upsert_station("ST-01")
        instrument_id = self.db.upsert_instrument(
            station_id, "P-01", "pressure", "MPa"
        )

        with self.assertRaises(ValueError):
            self.db.add_measurement(
                mission_id,
                station_id,
                instrument_id,
                "OK",
                value=0.5,
                confidence=1.5,
            )

    def test_station_and_instrument_upserts_are_stable(self):
        station_one = self.db.upsert_station("ST-01", "First")
        station_two = self.db.upsert_station("ST-01", "Updated")
        instrument_one = self.db.upsert_instrument(
            station_one, "P-01", "pressure", "MPa"
        )
        instrument_two = self.db.upsert_instrument(
            station_one, "P-01", "pressure", "MPa", norm_lo=0.2, norm_hi=1.0
        )

        self.assertEqual(station_one, station_two)
        self.assertEqual(instrument_one, instrument_two)


if __name__ == "__main__":
    unittest.main()
