"""Create a reproducible mixed teaching wind table; values are not observations."""
from pathlib import Path
import csv
import sys
from datetime import datetime, timedelta, timezone

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples/synthetic_wind_observations.csv"
NE_SW_OUTPUT = ROOT / "examples/synthetic_ne_sw_wind.csv"


def write_hourly_table(path, directions, speeds):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp_utc", "direction_from_deg", "wind_speed_m_s"])
        for index, (direction, speed) in enumerate(zip(directions, speeds)):
            timestamp = start + timedelta(hours=index)
            writer.writerow([timestamp.isoformat().replace("+00:00", "Z"),
                             f"{direction:.6f}", f"{speed:.6f}"])
    print(f"Wrote {len(directions)} synthetic hourly records to {path}")


def main():
    rng = np.random.default_rng(22001)
    observations = 1200
    # A mixed distribution demonstrates that table mode assumes no wind regime:
    # 70% has a northerly tendency and 30% covers all directions.
    prevailing = rng.random(observations) < .70
    directions = rng.uniform(0.0, 360.0, observations)
    directions[prevailing] = np.mod(
        rng.normal(loc=0.0, scale=40.0, size=prevailing.sum()), 360.0)
    speeds = np.clip(rng.weibull(2.0, observations) * 6.0, .2, 15.9)

    write_hourly_table(OUTPUT, directions, speeds)

    # Deliberately concentrated bidirectional case: 92% FROM NE, 8% FROM SW.
    rng = np.random.default_rng(22002)
    northeast_count = round(observations * .92)
    northeast = rng.normal(loc=45.0, scale=6.0, size=northeast_count)
    southwest = rng.normal(loc=225.0, scale=8.0,
                           size=observations - northeast_count)
    directions = np.mod(np.r_[northeast, southwest], 360.0)
    speeds = np.clip(rng.normal(loc=5.5, scale=1.2, size=observations), 1.0, 9.5)
    order = rng.permutation(observations)
    write_hourly_table(NE_SW_OUTPUT, directions[order], speeds[order])


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
