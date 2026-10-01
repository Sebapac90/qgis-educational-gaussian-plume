"""Exercise multi-source numerical and safety limits without QGIS."""
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaussian_spatial import locate_source, make_grid, make_grid_bounds
from gaussian_wind import (EmissionSource, mean_ground_concentration_sources,
                           wind_from_config)


def main():
    base = locate_source(-70.193195, -20.805320, calculation_crs=32719)
    grid = make_grid(base, width_m=10000, height_m=10000,
                     resolution_m=200)
    case_count = 0
    maximum_seen = 0.0
    for stability in "ABCDEF":
        for direction in (0.0, 45.0, 135.0, 225.0, 315.0):
            for speed in (0.5, 2.0, 10.0):
                wind = wind_from_config({
                    "wind_mode": "constant", "wind_speed_m_s": speed,
                    "wind_from_deg": direction})
                for source_count in (1, 3, 10, 25):
                    sources = []
                    for index in range(source_count):
                        column = index % 5
                        row = index // 5
                        source = replace(
                            base,
                            easting_m=(base.easting_m +
                                       (column - 2) * 350.0),
                            northing_m=(base.northing_m +
                                        (row - 2) * 275.0))
                        sources.append(EmissionSource(
                            source,
                            emission_kg_s=0.001 * (1 + index % 4),
                            effective_height_m=(10.0, 50.0, 200.0)[index % 3]))
                    values = mean_ground_concentration_sources(
                        grid, wind, sources, stability=stability,
                        direction_sectors=None,
                        max_evaluations=50_000_000)
                    valid = values[np.isfinite(values)]
                    if valid.size == 0 or np.any(valid < 0):
                        raise AssertionError(
                            (stability, direction, speed, source_count))
                    maximum_seen = max(maximum_seen, float(valid.max()))
                    case_count += 1

    limit_grid = make_grid_bounds(
        base, west_m=base.easting_m - 50000,
        south_m=base.northing_m - 50000,
        east_m=base.easting_m + 50000,
        north_m=base.northing_m + 50000, resolution_m=50)
    if limit_grid.shape != (2000, 2000):
        raise AssertionError(limit_grid.shape)
    try:
        make_grid(base, width_m=100001, height_m=100000,
                  resolution_m=100)
    except ValueError:
        spatial_limit_rejected = True
    else:
        spatial_limit_rejected = False

    heavy_wind = wind_from_config({
        "wind_mode": "prevailing", "wind_speed_m_s": 5.0,
        "wind_from_deg": 225.0, "wind_hours": 1200,
        "wind_direction_std_deg": 40.0, "wind_random_seed": 22001})
    heavy_sources = [EmissionSource(
        replace(base,
                easting_m=base.easting_m + (index % 5) * 100.0,
                northing_m=base.northing_m + (index // 5) * 100.0),
        emission_kg_s=.001, effective_height_m=50.0)
        for index in range(20)]
    try:
        mean_ground_concentration_sources(
            limit_grid, heavy_wind, heavy_sources, stability="D",
            max_evaluations=50_000_000)
    except ValueError as error:
        computational_error = str(error)
        computational_limit_rejected = "interactive limit" in str(error)
    else:
        computational_error = ""
        computational_limit_rejected = False

    passed = spatial_limit_rejected and computational_limit_rejected
    report = {
        "status": "passed" if passed else "failed",
        "finite_nonnegative_cases": case_count,
        "matrix": {
            "stabilities": 6, "directions": 5, "speeds": 3,
            "source_counts": [1, 3, 10, 25],
        },
        "maximum_seen_kg_m3": maximum_seen,
        "four_million_cell_boundary_shape": list(limit_grid.shape),
        "over_100_km_rejected": spatial_limit_rejected,
        "over_50_million_evaluations_rejected":
            computational_limit_rejected,
        "computational_error": computational_error,
    }
    output = ROOT / "validation/multisource_numerical_stress_0167.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
