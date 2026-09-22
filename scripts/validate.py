"""Run the test suite and write reproducible Masters 2008 sample results."""
import csv
import json
import math
import pathlib
import platform
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from gaussian_core import gaussian_concentration


# Independent transcription of Table 7.8 at x=1 km: sigma_y=a and
# sigma_z=c+f because every power of one equals one.
TABLE_7_8_AT_1_KM = {
    "A": (213.0, 440.8 + 9.27),
    "B": (156.0, 106.6 + 3.3),
    "C": (104.0, 61.0),
    "D": (68.0, 33.2 - 1.7),
    "E": (50.5, 22.8 - 1.3),
    "F": (34.0, 14.35 - .35),
}


def main():
    tests = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if not result.wasSuccessful():
        return 1

    output = ROOT / "validation"
    output.mkdir(exist_ok=True)
    rows = []
    for category in "ABCDEF":
        sy, sz = TABLE_7_8_AT_1_KM[category]
        expected = (.04 / (math.pi * 5. * sy * sz) *
                    math.exp(-(50. ** 2) / (2. * sz ** 2)))
        actual = float(gaussian_concentration(
            1000., 0., 0., emission_kg_s=.04, wind_speed_m_s=5.,
            effective_height_m=50., stability=category))
        rows.append(dict(
            stability=category, x_downwind_m=1000, y_crosswind_m=0,
            z_m=0, emission_kg_s=.04, wind_speed_m_s=5, height_m=50,
            expected_kg_m3=expected, core_kg_m3=actual,
            core_ug_m3=actual * 1.e9,
            relative_error=abs(actual - expected) / expected))
    with (output / "centreline_cases.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = dict(
        model="Masters and Ela (2008), equations 7.47-7.48, Table 7.8",
        python=platform.python_version(), numpy=np.__version__,
        tests_run=result.testsRun, failures=len(result.failures),
        errors=len(result.errors), centreline_cases=len(rows),
        max_relative_error_six_centreline_cases=max(
            row["relative_error"] for row in rows),
        scope="Equation and software checks; not field or regulatory validation")
    (output / "summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
