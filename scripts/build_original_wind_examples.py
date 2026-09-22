"""Build source-format wind extracts matching the six canonical examples."""
from pathlib import Path
import argparse
import csv


ROOT = Path(__file__).resolve().parents[1]
PERIODS = ("6h", "day", "month")
OUTPUT_NAMES = {
    "6h": "6_horas",
    "day": "1_dia",
    "month": "1_mes",
}


def write_dmc(source_directory, output_directory):
    outputs = []
    for period in PERIODS:
        source = source_directory / f"dmc_{period}_source.csv"
        target = output_directory / (
            f"DGAC_DMC_formato_origen_{OUTPUT_NAMES[period]}.csv")
        with source.open(encoding="utf-8-sig", newline="") as input_stream:
            rows = list(csv.DictReader(input_stream))
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("Hora del día (local)",
                             "Dirección del Viento en °",
                             "Intensidad del Viento en Kph"))
            for row in rows:
                date, time = row["fecha_hora_local"].split()
                day = date.split("-", 1)[0]
                writer.writerow((f"{day} ({time})", row["direccion_grados"],
                                 row["velocidad_km_h"]))
        outputs.append(target)
    return outputs


def write_noaa(source_directory, noaa_csv, output_directory):
    targets = {}
    wanted = {}
    for period in PERIODS:
        source = source_directory / f"noaa_{period}_source.csv"
        with source.open(encoding="utf-8-sig", newline="") as stream:
            wanted[period] = {row["DATE"] for row in csv.DictReader(stream)}
        target = output_directory / (
            f"NOAA_formato_original_{OUTPUT_NAMES[period]}.csv")
        targets[period] = target

    selected = {period: [] for period in PERIODS}
    with noaa_csv.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["REPORT_TYPE"].strip() != "FM-15":
                continue
            for period in PERIODS:
                if row["DATE"] in wanted[period]:
                    selected[period].append(row)

    for period in PERIODS:
        if len(selected[period]) != len(wanted[period]):
            raise ValueError(
                f"NOAA {period}: expected {len(wanted[period])} rows, "
                f"found {len(selected[period])}")
        with targets[period].open(
                "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames,
                                    quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(selected[period])
    return list(targets.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-directory", type=Path,
        default=ROOT / "examples/real_wind")
    parser.add_argument("--noaa-csv", type=Path, required=True)
    parser.add_argument(
        "--output-directory", type=Path,
        default=ROOT / "outputs/pruebas_manuales_viento")
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    outputs = write_dmc(args.source_directory, args.output_directory)
    outputs += write_noaa(
        args.source_directory, args.noaa_csv, args.output_directory)
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
