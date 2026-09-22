"""Reproduce a domain sensitivity experiment; does not replace Patache outputs."""
from pathlib import Path
import json
import os
import sys

sys.dont_write_bytecode = True
if __name__ == "__main__":
    os.environ.pop("PROJ_LIB", None)
    os.environ.pop("PROJ_DATA", None)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from gaussian_spatial import locate_source_from_config, make_grid
from gaussian_wind import mean_ground_concentration, wind_from_config
from gaussian_units import (concentration_factor_from_kg_m3, display_from_config,
                            emission_from_config)


def main():
    config = json.loads((ROOT / "examples/patache.json").read_text())
    s, m = config["source"], config["model"]
    source = locate_source_from_config(s)
    _, _, q_kg_s = emission_from_config(m)
    wind = wind_from_config(m,base_dir=ROOT)
    concentration_unit, raster_minimum, _, _ = display_from_config(config)
    output_factor = concentration_factor_from_kg_m3(concentration_unit)
    rows = []
    # Even cell counts keep the same pixel centres in every overlapping domain.
    for side in (10000, 20000, 40000, 80000, 100000):
        grid = make_grid(source, width_m=side, height_m=side,
                         resolution_m=config["grid"]["resolution_m"])
        displayed = mean_ground_concentration(grid, wind, emission_kg_s=q_kg_s,
            effective_height_m=m["effective_height_m"],
            stability=m["stability"],
            wind_reference_height_m=m.get("wind_reference_height_m", 10.0),
            wind_exposure=m.get("wind_exposure", "rough")) * output_factor
        edges = dict(north=float(displayed[0].max()), south=float(displayed[-1].max()),
                     west=float(displayed[:, 0].max()), east=float(displayed[:, -1].max()))
        peak, edge = float(displayed.max()), max(edges.values())
        row = dict(side_m=side, cells=int(displayed.size), concentration_unit=concentration_unit,
            maximum_concentration=peak, edge_maxima_concentration=edges,
            border_to_peak=edge / peak if peak else None,
            visible_plume_reaches_domain_edge=edge >= raster_minimum)
        if concentration_unit == "ug/m3":
            row.update(maximum_ug_m3=peak, edge_maxima_ug_m3=edges)
        rows.append(row)
        del displayed
    report = dict(scenario=config, experiment="Centred squares; unchanged pixel spacing",
                  scope="Numerical sensitivity only; no empirical validity at long range",
                  results=rows)
    out = ROOT / "validation/domain_sensitivity.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
