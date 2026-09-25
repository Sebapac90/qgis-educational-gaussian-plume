"""Compare raw DGAC Iquique winds with the plugin's 5-degree aggregation."""
from pathlib import Path
import csv
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path.home() / "Downloads" / "DGAC IQUIQUE.csv"
OUTPUT = ROOT / "outputs" / "diagnostics" / "comparacion_dgac_iquique_estabilidad_F.png"


def read_records():
    records = []
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter=";"):
            try:
                direction = float(row["dd (°)"]) % 360.0
                speed_knots = float(row["ff (kt)"])
            except (KeyError, TypeError, ValueError):
                continue
            if speed_knots > 0:
                records.append((direction, speed_knots * 0.514444))
    return records


def main():
    from matplotlib import pyplot as plt
    from matplotlib.colors import LogNorm
    sys.path.insert(0, str(ROOT))
    from gaussian_core import masters_2008_wind_speed_at_height
    from gaussian_spatial import locate_source, make_grid
    from gaussian_wind import WindSeries, mean_ground_concentration

    sys.path.insert(0, str(ROOT / "reference" / "manchester" / "python"))
    from gauss_func import gauss_func

    records = read_records()
    if not records:
        raise ValueError("DGAC Iquique contains no directional winds")
    directions = np.array([direction for direction, _ in records])
    speeds = np.array([speed for _, speed in records])
    wind = WindSeries("table", directions, speeds,
                      np.full(len(records), 1.0 / len(records)),
                      None, None, None, "DGAC Iquique raw observations")
    source = locate_source(-70.193195, -20.805320, calculation_crs=32719)
    grid = make_grid(source, width_m=10000, height_m=10000, resolution_m=50)
    common = {
        "emission_kg_s": .04, "effective_height_m": 50., "stability": "F",
        "wind_reference_height_m": 10., "wind_exposure": "rough",
    }
    plugin_raw = mean_ground_concentration(
        grid, wind, direction_sectors=None, **common)
    plugin_grouped = mean_ground_concentration(grid, wind, **common)

    east, north = np.meshgrid(grid.east_centres_m - source.easting_m,
                              grid.north_centres_m - source.northing_m)
    wind_factor = float(masters_2008_wind_speed_at_height(
        1., 10., 50., "F", "rough"))
    manchester = np.zeros_like(east)
    for direction, speed in records:
        manchester += gauss_func(.04, speed * wind_factor, direction,
                                 east, north, np.zeros_like(east),
                                 0., 0., 50., 6)
    manchester /= len(records)

    for field in (plugin_raw, plugin_grouped):
        field[~np.isfinite(field)] = np.nan
    positive = np.concatenate([
        field[np.isfinite(field) & (field > 0)]
        for field in (plugin_raw, plugin_grouped, manchester)
    ])
    vmin = max(np.quantile(positive, .02), 1e-14)
    vmax = np.quantile(positive, .998)
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.4), sharex=True,
                                sharey=True, constrained_layout=True)
    panels = [
        ("Nuestro modelo: 478 filas, sin agrupar", plugin_raw),
        ("Nuestro plugin: 72 sectores de 5°", plugin_grouped),
        ("Manchester: 478 horas, sin agrupar", manchester),
    ]
    image = None
    for axis, (title, field) in zip(axes, panels):
        image = axis.imshow(
            field * 1e9, extent=(-5000, 5000, -5000, 5000), origin="lower",
            cmap="YlOrRd", norm=LogNorm(vmin=vmin * 1e9, vmax=vmax * 1e9))
        axis.plot(0, 0, marker="*", color="black", markersize=7)
        axis.set_title(title, fontsize=10)
        axis.set_xlabel("Este-Oeste respecto de la fuente (m)")
    axes[0].set_ylabel("Norte-Sur respecto de la fuente (m)")
    figure.colorbar(image, ax=axes, label="Concentración media (µg/m³)")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, dpi=180)
    plt.close(figure)

    valid = np.isfinite(plugin_raw) & (plugin_raw > np.nanmax(plugin_raw) * .001)
    relative = np.abs(plugin_grouped[valid] - plugin_raw[valid]) / plugin_raw[valid]
    print({
        "output": str(OUTPUT),
        "records": len(records),
        "plugin_raw_max_ug_m3": float(np.nanmax(plugin_raw) * 1e9),
        "plugin_grouped_max_ug_m3": float(np.nanmax(plugin_grouped) * 1e9),
        "grouping_peak_change_percent": float(
            (np.nanmax(plugin_grouped) / np.nanmax(plugin_raw) - 1.) * 100),
        "grouping_p95_relative_percent": float(np.quantile(relative, .95) * 100),
        "grouping_max_relative_percent": float(np.max(relative) * 100),
        "manchester_max_ug_m3": float(np.nanmax(manchester) * 1e9),
    })


if __name__ == "__main__":
    main()
