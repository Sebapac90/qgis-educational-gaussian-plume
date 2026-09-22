import csv
import tempfile
import unittest
from pathlib import Path

from gaussian_wind_import import normalize_wind_csv, read_wind_csv_preview


class WindImportTests(unittest.TestCase):
    def test_local_time_kmh_and_direction_to_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "origen.csv"
            output = Path(directory) / "normalizado.csv"
            source.write_text(
                "fecha;direccion;rapidez\n"
                "19-09-2026 08:00;360;36,0\n"
                "19-09-2026 09:00;90;18,0\n", encoding="utf-8")
            summary = normalize_wind_csv(
                source, output, timestamp_column="fecha",
                direction_column="direccion", speed_column="rapidez",
                speed_unit="km/h", timezone_name="America/Santiago",
                date_format="%d-%m-%Y %H:%M", direction_convention="to")
            with output.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(summary.rows, 2)
            self.assertEqual(summary.predominant_interval_seconds, 3600)
            self.assertEqual(rows[0]["timestamp_utc"], "2026-09-19T11:00:00Z")
            self.assertEqual(float(rows[0]["direction_from_deg"]), 180)
            self.assertEqual(float(rows[0]["wind_speed_m_s"]), 10)
            self.assertEqual(float(rows[1]["direction_from_deg"]), 270)
            self.assertEqual(float(rows[1]["wind_speed_m_s"]), 5)
            self.assertEqual(rows[0]["source_total_rows"], "2")
            self.assertEqual(rows[0]["excluded_calm_rows"], "0")

    def test_timezone_is_required_for_naive_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "origen.csv"
            source.write_text("date,dir,speed\n2025-01-01 00:00,10,2\n")
            with self.assertRaisesRegex(ValueError, "select a time zone"):
                normalize_wind_csv(
                    source, Path(directory) / "out.csv", timestamp_column="date",
                    direction_column="dir", speed_column="speed", speed_unit="m/s")

    def test_day_month_year_with_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "origen.csv"
            output = Path(directory) / "normalizado.csv"
            source.write_text(
                "fecha,direccion,rapidez\n"
                "01-09-2026 00:00:00,180,5\n", encoding="utf-8")
            summary = normalize_wind_csv(
                source, output, timestamp_column="fecha",
                direction_column="direccion", speed_column="rapidez",
                speed_unit="m/s", timezone_name="America/Santiago",
                date_format="%d-%m-%Y %H:%M:%S")
            self.assertEqual(summary.rows, 1)
            with output.open(newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["timestamp_utc"], "2026-09-01T04:00:00Z")

    def test_selected_columns_and_ranges_are_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "origen.csv"
            source.write_text("date,dir,speed\n2025-01-01T00:00:00Z,361,2\n")
            with self.assertRaisesRegex(ValueError, "between 0 and 360"):
                normalize_wind_csv(
                    source, Path(directory) / "out.csv", timestamp_column="date",
                    direction_column="dir", speed_column="speed", speed_unit="m/s")

    def test_preview_cardinals_and_declared_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "origen.csv"
            output = Path(directory) / "normalizado.csv"
            source.write_text(
                "momento;rumbo;velocidad\n"
                "01/01/2025 00:00;NE;10\n"
                "01/01/2025 01:00;VRB;12\n"
                "01/01/2025 02:00;S;0\n"
                "01/01/2025 03:00;-;-\n",
                encoding="utf-8")
            headers, preview = read_wind_csv_preview(source, limit=2)
            self.assertEqual(headers, ["momento", "rumbo", "velocidad"])
            self.assertEqual(len(preview), 2)
            summary = normalize_wind_csv(
                source, output, timestamp_column="momento",
                direction_column="rumbo", speed_column="velocidad",
                speed_unit="kn", timezone_name="UTC",
                date_format="%d/%m/%Y %H:%M", direction_format="cardinal",
                variable_tokens="VRB, .", missing_tokens="-")
            self.assertEqual(summary.total_rows, 4)
            self.assertEqual(summary.rows, 1)
            self.assertEqual(summary.excluded_variable_rows, 1)
            self.assertEqual(summary.excluded_calm_rows, 1)
            self.assertEqual(summary.excluded_missing_rows, 1)
            with output.open(newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(float(row["direction_from_deg"]), 45.)
            self.assertAlmostEqual(float(row["wind_speed_m_s"]), 5.14444)
            self.assertEqual(row["source_total_rows"], "4")
            self.assertEqual(row["excluded_calm_rows"], "1")
            self.assertEqual(row["excluded_variable_rows"], "1")
            self.assertEqual(row["excluded_missing_rows"], "1")

    def test_dgac_dot_direction_can_be_declared_variable(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dgac.csv"
            output = Path(directory) / "normalizado.csv"
            source.write_text(
                "fecha;dd;ff\n"
                "01-09-2026 08:00;.;1\n"
                "01-09-2026 09:00;300;4\n", encoding="utf-8")
            summary = normalize_wind_csv(
                source, output, timestamp_column="fecha",
                direction_column="dd", speed_column="ff", speed_unit="kn",
                timezone_name="UTC", date_format="%d-%m-%Y %H:%M",
                variable_tokens="VRB, .")
            self.assertEqual(summary.total_rows, 2)
            self.assertEqual(summary.rows, 1)
            self.assertEqual(summary.excluded_variable_rows, 1)


if __name__ == "__main__":
    unittest.main()
