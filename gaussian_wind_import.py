# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Normalize user-selected wind CSV columns without depending on QGIS."""
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
import csv
import math


SPEED_FACTORS_TO_M_S = {
    "m/s": 1.0,
    "km/h": 1.0 / 3.6,
    "kn": 0.514444,
    "kt": 0.514444,
    "knot": 0.514444,
    "knots": 0.514444,
    "nudos": 0.514444,
}

CARDINAL_DIRECTIONS_DEG = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SO": 225.0, "SW": 225.0,
    "WSW": 247.5, "OSO": 247.5, "W": 270.0, "O": 270.0,
    "WNW": 292.5, "ONO": 292.5, "NW": 315.0, "NO": 315.0,
    "NNW": 337.5, "NNO": 337.5,
}


@dataclass(frozen=True)
class WindImportSummary:
    total_rows: int
    rows: int
    excluded_calm_rows: int
    excluded_variable_rows: int
    excluded_missing_rows: int
    start_utc: str
    end_utc: str
    predominant_interval_seconds: Optional[int]
    irregular_intervals: int
    speed_unit_original: str
    direction_convention_original: str

    def as_dict(self):
        return asdict(self)


def _number(value, *, field, line):
    text = str(value).strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{field} line {line} is not numeric: {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"{field} line {line} must be finite")
    return number


def _timestamp(value, *, date_format, timezone_name, line):
    text = str(value).strip()
    try:
        if date_format:
            parsed = datetime.strptime(text, date_format)
        else:
            parsed = datetime.fromisoformat(
                text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as error:
        raise ValueError(f"timestamp line {line} is invalid: {error}") from None
    if parsed.tzinfo is None:
        if not timezone_name:
            raise ValueError(
                f"timestamp line {line} has no UTC offset; select a time zone")
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except Exception as error:
            raise ValueError(f"unknown time zone {timezone_name!r}: {error}") from None
    return parsed.astimezone(timezone.utc)


def _tokens(values):
    if values is None:
        return set()
    if isinstance(values, str):
        values = values.split(",")
    return {str(value).strip().casefold() for value in values
            if str(value).strip()}


def _direction(value, *, direction_format, field, line):
    if direction_format == "degrees":
        direction = _number(value, field=field, line=line)
        if not 0 <= direction <= 360:
            raise ValueError(f"{field} line {line} must be between 0 and 360")
        return direction % 360
    if direction_format == "cardinal":
        token = str(value).strip().upper().replace(" ", "")
        if token not in CARDINAL_DIRECTIONS_DEG:
            raise ValueError(
                f"{field} line {line} is not a supported cardinal direction")
        return CARDINAL_DIRECTIONS_DEG[token]
    raise ValueError("direction_format must be degrees or cardinal")


def read_wind_csv_preview(source_path, *, limit=8):
    """Return detected headers and a small row preview for a CSV/TSV file."""
    source = Path(source_path)
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        headers = list(reader.fieldnames or [])
        rows = []
        for index, row in enumerate(reader):
            if index >= limit:
                break
            rows.append([row.get(header, "") for header in headers])
    if len(headers) < 3:
        raise ValueError("Wind CSV must contain at least three named columns")
    return headers, rows


def normalize_wind_csv(source_path, output_path, *, timestamp_column,
                       direction_column, speed_column, speed_unit,
                       timezone_name=None, date_format=None,
                       direction_convention="from",
                       direction_format="degrees", calm_tokens=None,
                       variable_tokens=None, missing_tokens=None):
    """Map a source CSV to the canonical UTC/degrees-from/m/s schema."""
    unit = str(speed_unit).strip().lower()
    if unit not in SPEED_FACTORS_TO_M_S:
        raise ValueError("speed_unit must be m/s, km/h or knots")
    convention = str(direction_convention).strip().lower()
    if convention not in {"from", "to"}:
        raise ValueError("direction_convention must be 'from' or 'to'")

    source = Path(source_path)
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        required = {timestamp_column, direction_column, speed_column}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV is missing selected columns: " +
                             ", ".join(sorted(missing)))
        rows = []
        total_rows = 0
        excluded_calm = 0
        excluded_variable = 0
        excluded_missing = 0
        calm = _tokens(calm_tokens)
        variable = _tokens(variable_tokens)
        missing_values = _tokens(missing_tokens) | {""}
        timestamps = set()
        for line, row in enumerate(reader, start=2):
            total_rows += 1
            raw_timestamp = str(row[timestamp_column]).strip()
            raw_direction = str(row[direction_column]).strip()
            raw_speed = str(row[speed_column]).strip()
            folded = {raw_timestamp.casefold(), raw_direction.casefold(),
                      raw_speed.casefold()}
            if folded & missing_values:
                excluded_missing += 1
                continue
            if (raw_direction.casefold() in variable or
                    raw_speed.casefold() in variable):
                excluded_variable += 1
                continue
            if (raw_direction.casefold() in calm or
                    raw_speed.casefold() in calm):
                excluded_calm += 1
                continue
            instant = _timestamp(row[timestamp_column], date_format=date_format,
                                 timezone_name=timezone_name, line=line)
            if instant in timestamps:
                raise ValueError(f"timestamp line {line} is duplicated")
            timestamps.add(instant)
            direction = _direction(
                row[direction_column], direction_format=direction_format,
                field=direction_column, line=line)
            if convention == "to":
                direction = (direction + 180) % 360
            speed = (_number(row[speed_column], field=speed_column, line=line) *
                     SPEED_FACTORS_TO_M_S[unit])
            if speed == 0:
                excluded_calm += 1
                continue
            if speed < 0:
                raise ValueError(f"{speed_column} line {line} must be nonnegative")
            rows.append((instant, direction, speed))
    if not rows:
        raise ValueError("CSV has no wind observations")
    rows.sort(key=lambda item: item[0])

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("timestamp_utc", "direction_from_deg", "wind_speed_m_s",
                         "source_total_rows", "excluded_calm_rows",
                         "excluded_variable_rows", "excluded_missing_rows"))
        for instant, direction, speed in rows:
            writer.writerow((instant.isoformat().replace("+00:00", "Z"),
                             f"{direction:.6f}", f"{speed:.6f}", total_rows,
                             excluded_calm, excluded_variable,
                             excluded_missing))

    differences = [int((later[0] - earlier[0]).total_seconds())
                   for earlier, later in zip(rows, rows[1:])]
    interval = Counter(differences).most_common(1)[0][0] if differences else None
    irregular = sum(value != interval for value in differences)
    return WindImportSummary(
        total_rows=total_rows,
        rows=len(rows),
        excluded_calm_rows=excluded_calm,
        excluded_variable_rows=excluded_variable,
        excluded_missing_rows=excluded_missing,
        start_utc=rows[0][0].isoformat().replace("+00:00", "Z"),
        end_utc=rows[-1][0].isoformat().replace("+00:00", "Z"),
        predominant_interval_seconds=interval,
        irregular_intervals=irregular,
        speed_unit_original=speed_unit,
        direction_convention_original=convention,
    )
