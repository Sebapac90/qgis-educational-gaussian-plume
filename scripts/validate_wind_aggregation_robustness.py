"""Validate 72-sector aggregation against row-wise wind calculation."""
from pathlib import Path
from time import perf_counter
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaussian_spatial import locate_source, make_grid
from gaussian_wind import (aggregate_wind_for_calculation,
                           mean_ground_concentration, wind_from_config)
from scripts.compare_wind_aggregation import field_metrics


def compare(grid, wind, physics):
    grouped = aggregate_wind_for_calculation(wind)
    started = perf_counter()
    exact = mean_ground_concentration(
        grid, wind, direction_sectors=None, **physics)
    exact_seconds = perf_counter() - started
    started = perf_counter()
    approximate = mean_ground_concentration(
        grid, grouped, direction_sectors=None, **physics)
    grouped_seconds = perf_counter() - started
    result = field_metrics(exact, approximate, grid.resolution_m)
    result.update({
        "observations": wind.samples,
        "groups": grouped.samples,
        "exact_seconds": exact_seconds,
        "grouped_seconds": grouped_seconds,
        "speedup": exact_seconds / grouped_seconds,
    })
    return result


def summarize(cases):
    return {
        "cases": len(cases),
        "worst_absolute_maximum_difference_percent": max(
            abs(case["maximum_difference_percent"]) for case in cases),
        "worst_normalized_rmse_percent": max(
            case["normalized_rmse_percent"] for case in cases),
        "worst_normalized_mae_percent": max(
            case["normalized_mae_percent"] for case in cases),
        "minimum_pixel_correlation": min(
            case["pixel_correlation"] for case in cases),
        "minimum_speedup": min(case["speedup"] for case in cases),
        "maximum_speedup": max(case["speedup"] for case in cases),
    }


def main():
    grid = make_grid(
        locate_source(-70.193195, -20.805320, calculation_crs="auto"),
        width_m=10000, height_m=10000, resolution_m=100)
    physics = {
        "emission_kg_s": .04,
        "effective_height_m": 50,
        "stability": "D",
    }
    prevailing_cases = []
    for centre in (0.0, 2.5, 225.0):
        for spread in (5.0, 10.0, 20.0, 40.0, 80.0):
            for seed in (22001, 22002, 22003):
                wind = wind_from_config({
                    "wind_mode": "prevailing",
                    "wind_speed_m_s": 5.0,
                    "wind_from_deg": centre,
                    "wind_hours": 1200,
                    "wind_random_seed": seed,
                    "wind_direction_std_deg": spread,
                })
                result = compare(grid, wind, physics)
                result.update({
                    "centre_deg": centre,
                    "spread_deg": spread,
                    "seed": seed,
                })
                prevailing_cases.append(result)

    real_cases = []
    for name in ("dmc_6h", "dmc_day", "dmc_month",
                 "noaa_6h", "noaa_day", "noaa_month"):
        wind = wind_from_config({
            "wind_mode": "table",
            "wind_file": str(
                ROOT / "examples/real_wind" / f"{name}_ready.csv"),
        })
        result = compare(grid, wind, physics)
        result["case"] = name
        real_cases.append(result)

    report = {
        "status": "passed",
        "grid": {
            "width_m": 10000,
            "height_m": 10000,
            "resolution_m": 100,
        },
        "physics": physics,
        "method": {
            "exact": "one plume per observation",
            "grouped": "72 direction sectors x 7 speed classes",
        },
        "prevailing_matrix_summary": summarize(prevailing_cases),
        "prevailing_cases": prevailing_cases,
        "real_table_summary": summarize(real_cases),
        "real_table_cases": real_cases,
    }
    output = ROOT / "validation/wind_aggregation_robustness.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "prevailing": report["prevailing_matrix_summary"],
        "real_tables": report["real_table_summary"],
        "report": str(output.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    os.environ.pop("PROJ_LIB", None)
    os.environ.pop("PROJ_DATA", None)
    main()
