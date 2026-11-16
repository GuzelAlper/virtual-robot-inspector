#!/usr/bin/env python3
"""SQLite storage for inspection missions and gauge readings.

The module has no third-party dependencies and can be used both from ROS 2 nodes
and from the command line:

    python3 inspection_db.py init --db ~/inspection_data/inspection.db
    python3 inspection_db.py demo --db ~/inspection_data/inspection.db
    python3 inspection_db.py show --db ~/inspection_data/inspection.db
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_text(value: Optional[Dict[str, Any]]) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


class InspectionDatabase:
    """Small repository layer around the inspection SQLite database."""

    def __init__(self, path: str):
        self.path = os.path.abspath(os.path.expanduser(path))
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS missions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_uuid TEXT NOT NULL UNIQUE,
                    scene TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_s REAL,
                    returned_to_start INTEGER,
                    error_reason TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS stations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_code TEXT NOT NULL UNIQUE,
                    title TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS instruments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id INTEGER NOT NULL,
                    instrument_code TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    min_value REAL,
                    max_value REAL,
                    norm_lo REAL,
                    norm_hi REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(station_id, instrument_code),
                    FOREIGN KEY(station_id) REFERENCES stations(id)
                );

                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id INTEGER NOT NULL,
                    station_id INTEGER NOT NULL,
                    instrument_id INTEGER NOT NULL,
                    checkpoint_code TEXT,
                    value REAL,
                    normalized_value REAL,
                    status TEXT NOT NULL,
                    confidence REAL,
                    image_path TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    captured_at TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    raw_result_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(mission_id) REFERENCES missions(id),
                    FOREIGN KEY(station_id) REFERENCES stations(id),
                    FOREIGN KEY(instrument_id) REFERENCES instruments(id)
                );

                CREATE TABLE IF NOT EXISTS mission_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_measurements_mission
                    ON measurements(mission_id);
                CREATE INDEX IF NOT EXISTS idx_measurements_instrument
                    ON measurements(instrument_id);
                CREATE INDEX IF NOT EXISTS idx_events_mission
                    ON mission_events(mission_id);
                """
            )
            row = db.execute("SELECT MAX(version) AS version FROM schema_info").fetchone()
            if row["version"] is None:
                db.execute(
                    "INSERT INTO schema_info(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )

    def start_mission(
        self,
        scene: str,
        metadata: Optional[Dict[str, Any]] = None,
        started_at: Optional[str] = None,
    ) -> int:
        mission_uuid = str(uuid.uuid4())
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO missions(
                    mission_uuid, scene, status, started_at, metadata_json
                ) VALUES (?, ?, 'RUNNING', ?, ?)
                """,
                (mission_uuid, scene, started_at or utc_now(), json_text(metadata)),
            )
            return int(cursor.lastrowid)

    def finish_mission(
        self,
        mission_id: int,
        status: str,
        duration_s: Optional[float] = None,
        returned_to_start: Optional[bool] = None,
        error_reason: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        returned = None if returned_to_start is None else int(returned_to_start)
        with self.connect() as db:
            cursor = db.execute(
                """
                UPDATE missions
                SET status = ?, finished_at = ?, duration_s = ?,
                    returned_to_start = ?, error_reason = ?
                WHERE id = ?
                """,
                (
                    status,
                    finished_at or utc_now(),
                    duration_s,
                    returned,
                    error_reason,
                    mission_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("mission not found: %s" % mission_id)

    def upsert_station(
        self,
        station_code: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO stations(station_code, title, metadata_json)
                VALUES (?, ?, ?)
                ON CONFLICT(station_code) DO UPDATE SET
                    title = excluded.title,
                    metadata_json = excluded.metadata_json
                """,
                (station_code, title, json_text(metadata)),
            )
            row = db.execute(
                "SELECT id FROM stations WHERE station_code = ?", (station_code,)
            ).fetchone()
            return int(row["id"])

    def upsert_instrument(
        self,
        station_id: int,
        instrument_code: str,
        instrument_type: str,
        unit: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        norm_lo: Optional[float] = None,
        norm_hi: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO instruments(
                    station_id, instrument_code, instrument_type, unit,
                    min_value, max_value, norm_lo, norm_hi, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_id, instrument_code) DO UPDATE SET
                    instrument_type = excluded.instrument_type,
                    unit = excluded.unit,
                    min_value = excluded.min_value,
                    max_value = excluded.max_value,
                    norm_lo = excluded.norm_lo,
                    norm_hi = excluded.norm_hi,
                    metadata_json = excluded.metadata_json
                """,
                (
                    station_id,
                    instrument_code,
                    instrument_type,
                    unit,
                    min_value,
                    max_value,
                    norm_lo,
                    norm_hi,
                    json_text(metadata),
                ),
            )
            row = db.execute(
                """
                SELECT id FROM instruments
                WHERE station_id = ? AND instrument_code = ?
                """,
                (station_id, instrument_code),
            ).fetchone()
            return int(row["id"])

    def add_measurement(
        self,
        mission_id: int,
        station_id: int,
        instrument_id: int,
        status: str,
        value: Optional[float] = None,
        normalized_value: Optional[float] = None,
        confidence: Optional[float] = None,
        image_path: Optional[str] = None,
        checkpoint_code: Optional[str] = None,
        attempt: int = 1,
        captured_at: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        raw_result: Optional[Dict[str, Any]] = None,
    ) -> int:
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO measurements(
                    mission_id, station_id, instrument_id, checkpoint_code,
                    value, normalized_value, status, confidence, image_path,
                    attempt, captured_at, error_code, error_message,
                    raw_result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    station_id,
                    instrument_id,
                    checkpoint_code,
                    value,
                    normalized_value,
                    status,
                    confidence,
                    image_path,
                    attempt,
                    captured_at or utc_now(),
                    error_code,
                    error_message,
                    json_text(raw_result),
                ),
            )
            return int(cursor.lastrowid)

    def add_event(
        self,
        mission_id: int,
        event_type: str,
        message: str,
        severity: str = "INFO",
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO mission_events(
                    mission_id, event_type, severity, message,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    event_type,
                    severity,
                    message,
                    json_text(payload),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def mission_summary(self, mission_id: int) -> Dict[str, Any]:
        with self.connect() as db:
            mission = db.execute(
                "SELECT * FROM missions WHERE id = ?", (mission_id,)
            ).fetchone()
            if mission is None:
                raise ValueError("mission not found: %s" % mission_id)
            measurements = db.execute(
                """
                SELECT
                    m.*, s.station_code, s.title AS station_title,
                    i.instrument_code, i.instrument_type, i.unit,
                    i.min_value, i.max_value, i.norm_lo, i.norm_hi
                FROM measurements AS m
                JOIN stations AS s ON s.id = m.station_id
                JOIN instruments AS i ON i.id = m.instrument_id
                WHERE m.mission_id = ?
                ORDER BY m.id
                """,
                (mission_id,),
            ).fetchall()
            events = db.execute(
                "SELECT * FROM mission_events WHERE mission_id = ? ORDER BY id",
                (mission_id,),
            ).fetchall()
        return {
            "mission": dict(mission),
            "measurements": [dict(row) for row in measurements],
            "events": [dict(row) for row in events],
        }

    def list_missions(self) -> List[Dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT m.*,
                       COUNT(ms.id) AS measurement_count
                FROM missions AS m
                LEFT JOIN measurements AS ms ON ms.mission_id = m.id
                GROUP BY m.id
                ORDER BY m.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]


DEMO_INSTRUMENTS: Iterable[Dict[str, Any]] = (
    {"code": "P-01", "type": "pressure", "unit": "МПа", "range": (0.0, 1.6), "norm": (0.2, 1.0), "value": 0.62, "confidence": 0.97},
    {"code": "T-01", "type": "temperature", "unit": "°C", "range": (0.0, 120.0), "norm": (10.0, 80.0), "value": 46.0, "confidence": 0.95},
    {"code": "P-02", "type": "pressure", "unit": "бар", "range": (0.0, 10.0), "norm": (1.0, 6.0), "value": 7.8, "confidence": 0.96},
    {"code": "V-01", "type": "vacuum", "unit": "МПа", "range": (-0.1, 0.0), "norm": (-0.08, -0.02), "value": -0.05, "confidence": 0.94},
)


def create_demo(db: InspectionDatabase) -> int:
    mission_id = db.start_mission("inspection_hall_v1", {"source": "demo"})
    station_id = db.upsert_station("ST-01", "Тестовая станция")
    for item in DEMO_INSTRUMENTS:
        low, high = item["range"]
        norm_lo, norm_hi = item["norm"]
        value = float(item["value"])
        instrument_id = db.upsert_instrument(
            station_id,
            str(item["code"]),
            str(item["type"]),
            str(item["unit"]),
            low,
            high,
            norm_lo,
            norm_hi,
        )
        normalized = (value - low) / (high - low)
        status = "OK" if norm_lo <= value <= norm_hi else "ALARM"
        db.add_measurement(
            mission_id,
            station_id,
            instrument_id,
            status,
            value=value,
            normalized_value=normalized,
            confidence=float(item["confidence"]),
            image_path="images/%s.png" % item["code"].lower(),
            checkpoint_code="CP-%02d" % (len(db.mission_summary(mission_id)["measurements"]) + 1),
            raw_result={"source": "demo"},
        )
    db.add_event(mission_id, "MISSION_COMPLETED", "Демонстрационная миссия завершена")
    db.finish_mission(mission_id, "COMPLETED", duration_s=42.0, returned_to_start=True)
    return mission_id


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Inspection SQLite database")
    parser.add_argument("command", choices=("init", "demo", "show"))
    parser.add_argument(
        "--db",
        default="~/inspection_data/inspection.db",
        help="path to the SQLite database",
    )
    parser.add_argument("--mission", type=int, help="mission id for show")
    args = parser.parse_args()

    database = InspectionDatabase(args.db)
    if args.command == "init":
        print("Database ready: %s" % database.path)
    elif args.command == "demo":
        mission_id = create_demo(database)
        print("Demo mission created: %s" % mission_id)
        print(json.dumps(database.mission_summary(mission_id), ensure_ascii=False, indent=2))
    elif args.mission is not None:
        print(json.dumps(database.mission_summary(args.mission), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(database.list_missions(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
