"""Convert a MeteoChile HTML/XLS wind download to the plugin CSV schema."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


KNOT_TO_M_S = 0.514444
EXPECTED_HEADER = ["Fecha", "Hora (UTC)", "dd (°)", "ff (kt)", "VRB ()"]


class FirstTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.finished = False
        self.parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if self.finished:
            return
        if tag == "table" and not self.in_table:
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row = True
            self.row = []
        elif self.in_row and tag in {"th", "td"}:
            self.in_cell = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.finished:
            return
        if self.in_cell and tag in {"th", "td"}:
            self.row.append(" ".join("".join(self.parts).split()))
            self.in_cell = False
        elif self.in_row and tag == "tr":
            self.rows.append(self.row)
            self.in_row = False
        elif self.in_table and tag == "table":
            self.in_table = False
            self.finished = True


def read_table(path: Path) -> list[list[str]]:
    parser = FirstTableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    if not parser.rows or parser.rows[0] != EXPECTED_HEADER:
        found = parser.rows[0] if parser.rows else []
        raise ValueError(f"Unexpected MeteoChile header: {found}")
    return parser.rows[1:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source_rows = read_table(args.source)
    accepted: list[tuple[datetime, float, float]] = []
    excluded_variable = 0
    excluded_calm = 0
    excluded_both = 0
    timestamps: set[datetime] = set()

    for line, row in enumerate(source_rows, start=2):
        if len(row) != 5:
            raise ValueError(f"Line {line} does not have five columns")
        date_text, time_text, direction_text, speed_text, variable_text = row
        instant = datetime.strptime(
            f"{date_text} {time_text}", "%d-%m-%Y %H:%M"
        ).replace(tzinfo=timezone.utc)
        if instant in timestamps:
            raise ValueError(f"Duplicated timestamp at line {line}")
        timestamps.add(instant)

        speed_knots = float(speed_text)
        is_variable = variable_text.casefold() == "verdadero" or direction_text == "."
        is_calm = speed_knots <= 0
        if is_variable or is_calm:
            excluded_variable += int(is_variable)
            excluded_calm += int(is_calm)
            excluded_both += int(is_variable and is_calm)
            continue

        direction = float(direction_text)
        if not 0 <= direction <= 360:
            raise ValueError(f"Direction outside 0–360 at line {line}")
        accepted.append((instant, direction % 360, speed_knots * KNOT_TO_M_S))

    if not accepted:
        raise ValueError("No usable wind observations remain")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("timestamp_utc", "direction_from_deg", "wind_speed_m_s"))
        for instant, direction, speed in accepted:
            writer.writerow((
                instant.isoformat().replace("+00:00", "Z"),
                f"{direction:.6f}",
                f"{speed:.6f}",
            ))

    report_path = args.report or args.output.with_suffix(".json")
    report = {
        "source": str(args.source),
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "source_headers": EXPECTED_HEADER,
        "source_rows": len(source_rows),
        "accepted_rows": len(accepted),
        "excluded_variable_rows": excluded_variable,
        "excluded_calm_rows": excluded_calm,
        "excluded_as_variable_and_calm": excluded_both,
        "excluded_unique_rows": len(source_rows) - len(accepted),
        "conversion": {
            "timestamp": "Fecha + Hora (UTC) -> ISO 8601 UTC",
            "direction": "meteorological FROM; 360 degrees -> 0 degrees",
            "speed": f"ff (kt) * {KNOT_TO_M_S} -> m/s",
            "variable_policy": "excluded because no numeric direction is available",
            "calm_policy": "excluded because the stationary Gaussian core requires speed > 0",
        },
        "output": str(args.output),
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "period_utc": {
            "source_start": f"{source_rows[0][0]} {source_rows[0][1]}",
            "source_end": f"{source_rows[-1][0]} {source_rows[-1][1]}",
            "accepted_start": accepted[0][0].isoformat().replace("+00:00", "Z"),
            "accepted_end": accepted[-1][0].isoformat().replace("+00:00", "Z"),
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    print(report_path)


if __name__ == "__main__":
    main()
