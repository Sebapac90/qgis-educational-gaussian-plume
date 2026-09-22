"""Apply the documented MVP acceptance criteria to wind aggregation."""
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gaussian_wind import (CALCULATION_DIRECTION_SECTORS,
                           ROSE_DIRECTION_SECTORS)


def criterion(name, observed, relation, limit):
    if relation == "<=":
        passed = observed <= limit
    elif relation == ">=":
        passed = observed >= limit
    elif relation == "==":
        passed = observed == limit
    else:
        raise ValueError("Unsupported relation")
    return {"name": name, "observed": observed, "relation": relation,
            "limit": limit, "passed": bool(passed)}


def main():
    robustness = json.loads((
        ROOT / "validation/wind_aggregation_robustness.json").read_text())
    qgis = json.loads((
        ROOT / "validation/qgis_processing_algorithm.json").read_text())
    prevailing = robustness["prevailing_matrix_summary"]
    real = robustness["real_table_summary"]
    checks = [
        criterion("rose direction sectors", ROSE_DIRECTION_SECTORS,
                  "==", 16),
        criterion("calculation direction sectors",
                  CALCULATION_DIRECTION_SECTORS, "==", 72),
        criterion("prevailing worst maximum difference (%)",
                  prevailing["worst_absolute_maximum_difference_percent"],
                  "<=", 5.0),
        criterion("prevailing worst normalized RMSE (%)",
                  prevailing["worst_normalized_rmse_percent"], "<=", 1.0),
        criterion("prevailing minimum pixel correlation",
                  prevailing["minimum_pixel_correlation"], ">=", .995),
        criterion("prevailing minimum speedup",
                  prevailing["minimum_speedup"], ">=", 10.0),
        criterion("real tables worst maximum difference (%)",
                  real["worst_absolute_maximum_difference_percent"],
                  "<=", 5.0),
        criterion("real tables worst normalized RMSE (%)",
                  real["worst_normalized_rmse_percent"], "<=", 1.0),
        criterion("real tables minimum pixel correlation",
                  real["minimum_pixel_correlation"], ">=", .995),
        criterion("QGIS processing suite", qgis["status"],
                  "==", "passed"),
        criterion("QGIS CSV rose is PNG",
                  qgis["wind_csv"]["rose_is_png"], "==", True),
        criterion("QGIS CSV calculation classes below input rows",
                  qgis["wind_csv"]["calculation_classes"] <
                  qgis["wind_csv"]["samples"], "==", True),
    ]
    passed = all(check["passed"] for check in checks)
    report = {
        "status": "accepted" if passed else "rejected",
        "scope": "Educational MVP; not regulatory equivalence",
        "criteria_source": {
            "robustness": "validation/wind_aggregation_robustness.json",
            "qgis": "validation/qgis_processing_algorithm.json",
        },
        "manual_visual_review": {
            "artifact": "outputs/qgis_plugin/vista_mvp_040_viento_csv.png",
            "result": "passed",
            "observations": (
                "Continuous lobes and contours; no 16-sector radial banding"),
        },
        "checks": checks,
    }
    output = ROOT / "validation/wind_aggregation_acceptance.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
