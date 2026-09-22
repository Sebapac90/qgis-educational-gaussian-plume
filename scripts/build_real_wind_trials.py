"""Build six real-data wind import trials from downloaded DMC and NOAA files."""
from datetime import datetime
from pathlib import Path
import argparse
import csv
import json
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaussian_spatial import locate_source, make_grid
from gaussian_wind import (mean_ground_concentration, save_wind_rose,
                           wind_from_config)
from gaussian_wind_import import normalize_wind_csv


DMC_STATION = "Teniente Vidal, Coyhaique Ad. (450004)"
DMC_URL = ("https://climatologia.meteochile.gob.cl/application/diariob/"
           "graficosRecienteEma/450004/2026/08/{day}")
NOAA_STATION = "JFK International Airport, NY US (74486094789)"
NOAA_URL = ("https://www.ncei.noaa.gov/data/global-hourly/access/2025/"
            "74486094789.csv")


def _chart(html, identifier):
    block = html.split("Highcharts.chart('" + identifier + "'", 1)[1]
    categories = re.search(r"categories:\s*\[([^]]*)\]", block, re.S)
    data = re.search(r"data:\s*\[([^]]*)\]", block, re.S)
    if not categories or not data:
        raise ValueError(f"DMC chart {identifier} has no embedded data")
    labels = json.loads("[" + categories.group(1).rstrip(", \n") + "]")
    values = json.loads("[" + data.group(1).rstrip(", \n") + "]")
    if len(labels) != len(values):
        raise ValueError(f"DMC chart {identifier} labels and values differ")
    return labels, values


def dmc_month(html_directory):
    rows = {}
    for day in range(1, 32):
        path = Path(html_directory) / f"{day:02d}.html"
        html = path.read_text(encoding="utf-8")
        direction_labels, directions = _chart(html, "direccionViento")
        speed_labels, speeds = _chart(html, "intensidadViento")
        if direction_labels != speed_labels:
            raise ValueError(f"DMC chart timestamps differ on day {day}")
        prefix = f"{day:02d} ("
        for label, direction, speed in zip(direction_labels, directions, speeds):
            if (not label.startswith(prefix) or direction is None or speed is None or
                    float(speed) <= 0):
                continue
            hour, minute = map(int, label[4:-1].split(":"))
            if minute % 15:
                continue
            instant = datetime(2026, 8, day, hour, minute)
            rows[instant] = (float(direction), float(speed))
    return [(instant, *rows[instant]) for instant in sorted(rows)]


def noaa_month(csv_path):
    rows = {}
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            instant = datetime.fromisoformat(row["DATE"])
            if not (instant.year == 2025 and instant.month == 1):
                continue
            if row["REPORT_TYPE"].strip() != "FM-15":
                continue
            parts = row["WND"].split(",")
            if len(parts) < 5:
                continue
            direction = int(parts[0])
            speed_tenths = int(parts[3])
            if direction == 999 or speed_tenths in {0, 9999}:
                continue
            rows.setdefault(instant, (float(direction), speed_tenths / 10.0))
    return [(instant, *rows[instant]) for instant in sorted(rows)]


def _subset(rows, start, end):
    return [row for row in rows if start <= row[0] < end]


def _write_source(path, rows, *, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        if source == "dmc":
            writer.writerow(("fecha_hora_local", "direccion_grados",
                             "velocidad_km_h"))
            for instant, direction, speed in rows:
                writer.writerow((instant.strftime("%d-%m-%Y %H:%M"),
                                 f"{direction:g}", f"{speed:g}"))
        else:
            writer.writerow(("DATE", "WIND_DIRECTION_DEG", "WIND_SPEED_M_S"))
            for instant, direction, speed in rows:
                writer.writerow((instant.isoformat(timespec="seconds"),
                                 f"{direction:g}", f"{speed:g}"))


def _trial(name, rows, *, source, output_directory):
    source_path = output_directory / f"{name}_source.csv"
    ready_path = output_directory / f"{name}_ready.csv"
    rose_path = output_directory / f"{name}_rose.png"
    _write_source(source_path, rows, source=source)
    if source == "dmc":
        summary = normalize_wind_csv(
            source_path, ready_path, timestamp_column="fecha_hora_local",
            direction_column="direccion_grados", speed_column="velocidad_km_h",
            speed_unit="km/h", timezone_name="America/Santiago",
            date_format="%d-%m-%Y %H:%M")
    else:
        summary = normalize_wind_csv(
            source_path, ready_path, timestamp_column="DATE",
            direction_column="WIND_DIRECTION_DEG", speed_column="WIND_SPEED_M_S",
            speed_unit="m/s", timezone_name="UTC")
    wind = wind_from_config({"wind_mode": "table", "wind_file": str(ready_path)})
    save_wind_rose(wind, rose_path)
    receptor_source = locate_source(-70.193195, -20.805320,
                                    calculation_crs="auto")
    grid = make_grid(receptor_source, width_m=2000, height_m=2000,
                     resolution_m=100)
    concentration = mean_ground_concentration(
        grid, wind, emission_kg_s=.04, effective_height_m=50, stability="D",
        max_evaluations=50_000_000)
    if not np.all(np.isfinite(concentration)):
        raise ValueError(f"trial {name} produced non-finite concentration")
    result = summary.as_dict()
    result.update({
        "source_csv": str(source_path.relative_to(ROOT)),
        "ready_csv": str(ready_path.relative_to(ROOT)),
        "wind_rose": str(rose_path.relative_to(ROOT)),
        "representative_from_deg": wind.representative_from_deg,
        "mean_speed_m_s": wind.mean_speed_m_s,
        "calculation_test": {
            "source": "Patache teaching coordinate",
            "grid": "2 km x 2 km at 100 m",
            "emission_kg_s": 0.04,
            "effective_height_m": 50,
            "stability": "D",
            "maximum_kg_m3": float(concentration.max()),
        },
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmc-html-dir", required=True)
    parser.add_argument("--noaa-csv", required=True)
    args = parser.parse_args()
    output = ROOT / "examples" / "real_wind"
    output.mkdir(parents=True, exist_ok=True)

    dmc = dmc_month(args.dmc_html_dir)
    noaa = noaa_month(args.noaa_csv)
    definitions = {
        "dmc_6h": (_subset(dmc, datetime(2026, 8, 1, 6),
                           datetime(2026, 8, 1, 12)), "dmc"),
        "dmc_day": (_subset(dmc, datetime(2026, 8, 1),
                            datetime(2026, 8, 2)), "dmc"),
        "dmc_month": (dmc, "dmc"),
        "noaa_6h": (_subset(noaa, datetime(2025, 1, 15, 6),
                            datetime(2025, 1, 15, 12)), "noaa"),
        "noaa_day": (_subset(noaa, datetime(2025, 1, 15),
                             datetime(2025, 1, 16)), "noaa"),
        "noaa_month": (noaa, "noaa"),
    }
    report = {
        "status": "passed",
        "dmc": {
            "station": DMC_STATION,
            "source": DMC_URL.format(day="DD"),
            "source_interval": "1 minute; sampled every 15 minutes",
            "source_speed_unit": "km/h",
            "source_time_zone": "America/Santiago",
            "zero_speed_policy": "omitted because the stationary Gaussian core requires positive speed",
        },
        "noaa": {
            "station": NOAA_STATION,
            "source": NOAA_URL,
            "source_field": "hourly FM-15 WND decoded as direction degrees and tenths of m/s",
            "source_time_zone": "UTC",
            "zero_speed_policy": "omitted because the stationary Gaussian core requires positive speed",
        },
        "trials": {},
    }
    for name, (rows, source) in definitions.items():
        if not rows:
            raise ValueError(f"trial {name} has no valid rows")
        report["trials"][name] = _trial(
            name, rows, source=source, output_directory=output)

    report_path = ROOT / "validation" / "real_wind_import_trials.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
