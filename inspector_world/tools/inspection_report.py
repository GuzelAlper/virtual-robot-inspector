#!/usr/bin/env python3
"""Generate inspection reports from the project SQLite database."""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from inspection_db import InspectionDatabase


MEASUREMENT_COLUMNS = (
    "measurement_id",
    "mission_id",
    "station_code",
    "station_title",
    "checkpoint_code",
    "instrument_code",
    "instrument_type",
    "value",
    "unit",
    "normalized_value",
    "status",
    "confidence",
    "attempt",
    "captured_at",
    "image_path",
    "error_code",
    "error_message",
)


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _format_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _format_confidence(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def _clean_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    clean = {
        "mission": dict(summary["mission"]),
        "measurements": [dict(row) for row in summary["measurements"]],
        "events": [dict(row) for row in summary["events"]],
    }
    clean["mission"]["metadata"] = _decode_json(
        clean["mission"].pop("metadata_json", "{}")
    )
    for measurement in clean["measurements"]:
        measurement["raw_result"] = _decode_json(
            measurement.pop("raw_result_json", "{}")
        )
    for event in clean["events"]:
        event["payload"] = _decode_json(event.pop("payload_json", "{}"))
    return clean


def _measurement_rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    mission_id = summary["mission"]["id"]
    rows: List[Dict[str, Any]] = []
    for item in summary["measurements"]:
        rows.append(
            {
                "measurement_id": item["id"],
                "mission_id": mission_id,
                "station_code": item["station_code"],
                "station_title": item["station_title"],
                "checkpoint_code": item["checkpoint_code"],
                "instrument_code": item["instrument_code"],
                "instrument_type": item["instrument_type"],
                "value": item["value"],
                "unit": item["unit"],
                "normalized_value": item["normalized_value"],
                "status": item["status"],
                "confidence": item["confidence"],
                "attempt": item["attempt"],
                "captured_at": item["captured_at"],
                "image_path": item["image_path"],
                "error_code": item["error_code"],
                "error_message": item["error_message"],
            }
        )
    return rows


def _markdown(summary: Dict[str, Any]) -> str:
    mission = summary["mission"]
    measurements = summary["measurements"]
    events = summary["events"]
    alarm_count = sum(item["status"] == "ALARM" for item in measurements)
    error_count = sum(bool(item["error_code"] or item["error_message"]) for item in measurements)

    lines = [
        "# Отчёт об инспекции",
        "",
        "## Миссия",
        "",
        f"- ID: `{mission['id']}`",
        f"- UUID: `{mission['mission_uuid']}`",
        f"- Сцена: `{mission['scene']}`",
        f"- Статус: **{mission['status']}**",
        f"- Начало: {mission['started_at']}",
        f"- Завершение: {_format_value(mission['finished_at'])}",
        f"- Длительность: {_format_value(mission['duration_s'])} с",
        f"- Возврат на старт: {'да' if mission['returned_to_start'] else 'нет'}",
        f"- Причина ошибки: {_format_value(mission['error_reason'])}",
        "",
        "## Итог",
        "",
        f"- Измерений: **{len(measurements)}**",
        f"- Состояний ALARM: **{alarm_count}**",
        f"- Ошибок измерения: **{error_count}**",
        "",
        "## Измерения",
        "",
        "| Станция | Точка | Прибор | Значение | Статус | Уверенность | Попытка | Изображение |",
        "|---|---|---|---:|---|---:|---:|---|",
    ]
    for item in measurements:
        reading = f"{_format_value(item['value'])} {item['unit']}"
        lines.append(
            "| {station} | {checkpoint} | {instrument} | {reading} | {status} | "
            "{confidence} | {attempt} | {image} |".format(
                station=item["station_code"] or "—",
                checkpoint=item["checkpoint_code"] or "—",
                instrument=item["instrument_code"],
                reading=reading,
                status=item["status"],
                confidence=_format_confidence(item["confidence"]),
                attempt=item["attempt"],
                image=item["image_path"] or "—",
            )
        )

    lines.extend(["", "## События", ""])
    if events:
        lines.extend([
            "| Время | Важность | Тип | Сообщение |",
            "|---|---|---|---|",
        ])
        for event in events:
            lines.append(
                f"| {event['created_at']} | {event['severity']} | "
                f"{event['event_type']} | {event['message']} |"
            )
    else:
        lines.append("События не зарегистрированы.")
    lines.append("")
    return "\n".join(lines)


def generate_report(
    database: InspectionDatabase,
    mission_id: int,
    output_dir: str,
) -> Dict[str, str]:
    """Write Markdown, CSV and JSON reports for one mission."""
    output = Path(os.path.abspath(os.path.expanduser(output_dir)))
    output.mkdir(parents=True, exist_ok=True)
    summary = _clean_summary(database.mission_summary(mission_id))

    markdown_path = output / "report.md"
    csv_path = output / "measurements.csv"
    json_path = output / "mission.json"

    markdown_path.write_text(_markdown(summary), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MEASUREMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(_measurement_rows(summary))
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "markdown": str(markdown_path),
        "csv": str(csv_path),
        "json": str(json_path),
    }


def _latest_mission_id(database: InspectionDatabase) -> int:
    missions = database.list_missions()
    if not missions:
        raise ValueError("database contains no missions")
    return int(missions[0]["id"])


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Generate inspection mission report")
    parser.add_argument("--db", default="~/inspection_data/inspection.db")
    parser.add_argument("--mission", type=int, help="mission id; latest when omitted")
    parser.add_argument("--out", default="~/inspection_reports/latest")
    args = parser.parse_args()

    database = InspectionDatabase(args.db)
    mission_id = args.mission or _latest_mission_id(database)
    paths = generate_report(database, mission_id, args.out)
    print("Report generated for mission %s" % mission_id)
    for name, path in paths.items():
        print("%s: %s" % (name, path))


if __name__ == "__main__":
    main()
