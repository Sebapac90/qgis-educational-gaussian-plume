"""Extract wind-only examples from a MeteoChile monthly data sheet."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TableParser(HTMLParser):
    """Read the first HTML table while preserving its displayed cell text."""

    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.finished = False
        self.cell_parts: list[str] = []
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
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.finished:
            return
        if self.in_cell and tag in {"th", "td"}:
            self.row.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif self.in_row and tag == "tr":
            self.rows.append(self.row)
            self.in_row = False
        elif self.in_table and tag == "table":
            self.in_table = False
            self.finished = True


def read_rows(source: Path) -> tuple[list[str], list[str], list[list[str]]]:
    parser = TableParser()
    parser.feed(source.read_text(encoding="utf-8"))
    if len(parser.rows) < 3:
        raise ValueError("The downloaded sheet does not contain tabular data")

    group_header, field_header, *data_rows = parser.rows
    expected_group = ["Dia", "Hora", "Viento ( ° - kt.)"]
    if group_header[:3] != expected_group:
        raise ValueError(f"Unexpected MeteoChile group header: {group_header[:3]}")
    if field_header[:2] != ["DD Inst", "FF Inst"]:
        raise ValueError(f"Unexpected MeteoChile wind header: {field_header[:2]}")

    wind_rows = [row[:4] for row in data_rows]
    if any(len(row) != 4 for row in wind_rows):
        raise ValueError("At least one observation lacks the four wind columns")
    return group_header, field_header, wind_rows


def write_extract(target: Path, rows: list[list[str]]) -> None:
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        # The source uses rowspans for Dia/Hora and a colspan for Viento.
        # Two CSV rows retain that hierarchy without inventing field names.
        writer.writerow(("Dia", "Hora", "Viento ( ° - kt.)", ""))
        writer.writerow(("", "", "DD Inst", "FF Inst"))
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "outputs/pruebas_manuales_viento/meteochile_200006",
    )
    args = parser.parse_args()

    group_header, field_header, rows = read_rows(args.source)
    if len(rows) != 744:
        raise ValueError(f"Expected 744 hourly rows for August 2026, found {len(rows)}")

    expected_hours = {f"{hour:02d}:00" for hour in range(24)}
    for day in range(1, 32):
        day_rows = [row for row in rows if row[0] == f"{day:02d}"]
        if len(day_rows) != 24 or {row[1] for row in day_rows} != expected_hours:
            raise ValueError(f"Day {day:02d} is not a complete 24-hour series")

    args.output_directory.mkdir(parents=True, exist_ok=True)
    raw_target = args.output_directory / (
        "DMC_200006_2026-08_hoja_mensual_original.xls"
    )
    shutil.copy2(args.source, raw_target)

    periods = {
        "6_horas": rows[:6],
        "1_dia": rows[:24],
        "1_mes": rows,
    }
    outputs = []
    for label, period_rows in periods.items():
        target = args.output_directory / (
            f"DMC_200006_formato_original_{label}.csv"
        )
        write_extract(target, period_rows)
        outputs.append(target)

    metadata = {
        "source_institution": "Dirección Meteorológica de Chile (DMC)",
        "station": {
            "national_code": "200006",
            "name": "Diego Aracena Iquique Ap.",
            "wmo": "85418",
            "icao": "SCDA",
            "latitude": -20.549166,
            "longitude": -70.181110,
            "altitude_m": 48,
        },
        "period": "2026-08-01 00:00 to 2026-08-31 23:00",
        "time_zone": "not specified by the Hoja Mensual de Datos product",
        "frequency": "hourly",
        "rows": {label: len(value) for label, value in periods.items()},
        "source_quality": {
            "missing_DD_Inst": sum(not row[2] for row in rows),
            "missing_FF_Inst": sum(not row[3] for row in rows),
        },
        "original_headers": {
            "group": group_header,
            "fields": field_header,
            "wind_csv_rows": [
                ["Dia", "Hora", "Viento ( ° - kt.)", ""],
                ["", "", "DD Inst", "FF Inst"],
            ],
        },
        "wind_semantics": {
            "DD Inst": "instantaneous direction in degrees; source station metadata defines true direction from which wind blows",
            "FF Inst": "instantaneous speed in knots",
            "measurement_height_m": 10,
        },
        "source_urls": {
            "station": "https://climatologia.meteochile.gob.cl/application/informacion/fichaDeEstacion/200006",
            "product": "https://climatologia.meteochile.gob.cl/application/mensualb/hojaMensualDatos/200006/2026/8",
        },
        "notes": [
            "The raw .xls is the unmodified HTML download produced by MeteoChile.",
            "The CSV files select only day, hour, wind direction and wind speed; their two header rows preserve the source hierarchy.",
            "No calm, missing, or otherwise unusual source value was filtered.",
            "A blank DD Inst is preserved as published and must not be replaced by zero degrees during import.",
        ],
    }
    metadata_path = args.output_directory / "fuente_y_validacion.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for output in [raw_target, *outputs, metadata_path]:
        print(output)


if __name__ == "__main__":
    main()
