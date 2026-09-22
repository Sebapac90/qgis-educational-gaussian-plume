"""Run an explicit JSON scenario; outputs are reusable in QGIS.

CLI: python scripts/run_spatial_case.py [scenario.json]
Uses library-bundled PROJ databases for this process, avoiding old Anaconda
PROJ_LIB/PROJ_DATA overrides. Does not modify the user's global environment.
"""
from pathlib import Path
import json
import os
import sys

sys.dont_write_bytecode = True
if __name__ == "__main__":
    os.environ.pop("PROJ_LIB", None)
    os.environ.pop("PROJ_DATA", None)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from gaussian_spatial import locate_source_from_config, make_grid
from gaussian_wind import (aggregate_wind_for_calculation,
                           mean_ground_concentration, save_wind_rose,
                           wind_from_config)
from gaussian_raster import export_geotiff
from gaussian_map import create_map
from gaussian_contours import extract_isolines
from gaussian_units import (concentration_factor_from_kg_m3, display_from_config,
                            emission_from_config, unit_label)
from gaussian_core import masters_2008_wind_speed_at_height


def run_case(config, output_dir):
    """Source and meteorology come from config; coordinates are not hardcoded."""
    output_dir = Path(output_dir)
    s = config["source"]
    source = locate_source_from_config(s)
    grid = make_grid(source,**config["grid"])
    model = config["model"]
    emission_value, emission_unit, q_kg_s = emission_from_config(model)
    wind = wind_from_config(model,base_dir=ROOT)
    wind_reference_height = model.get("wind_reference_height_m", 10.0)
    wind_exposure = model.get("wind_exposure", "rough")
    wind_height_factor = float(masters_2008_wind_speed_at_height(
        1.0, wind_reference_height, model["effective_height_m"],
        model["stability"], wind_exposure))
    calculation_wind = aggregate_wind_for_calculation(wind)
    concentration_unit, raster_minimum, contour_minimum, contour_levels = display_from_config(config)
    concentration = mean_ground_concentration(grid,wind,emission_kg_s=q_kg_s,
        effective_height_m=model["effective_height_m"],stability=model["stability"],
        wind_reference_height_m=wind_reference_height,
        wind_exposure=wind_exposure)
    representative = wind.representative_from_deg
    tif_name = "pluma_" + concentration_unit.replace("/", "_") + ".tif"
    tif = export_geotiff(output_dir/tif_name,grid,concentration,metadata={
        "scenario":config["purpose"],"wind_mode":wind.mode,
        "wind_from_true_deg":representative if representative is not None else "variable",
        "wind_from_grid_deg":representative-source.convergence_deg if representative is not None else "variable",
        "wind_samples":wind.samples,"wind_calculation_classes":calculation_wind.samples,
        "wind_random_seed":wind.random_seed if wind.random_seed is not None else "none",
        "wind_mean_speed_m_s":wind.mean_speed_m_s,
        "wind_reference_height_m":wind_reference_height,
        "wind_exposure":wind_exposure,
        "wind_height_factor":wind_height_factor,
        "wind_model_mean_speed_m_s":wind.mean_speed_m_s * wind_height_factor,
        "emission_value":emission_value,"emission_unit":emission_unit,
        "emission_kg_s":q_kg_s,"wind_speed_m_s":wind.mean_speed_m_s,
        "height_m":model["effective_height_m"],"stability":model["stability"],
        "source_lon":source.longitude_deg,"source_lat":source.latitude_deg,
        "source_input_crs":source.input_crs.to_string(),
        "source_input_x":source.input_x,"source_input_y":source.input_y,
        "sampling":"pixel centre, not cell average"}, concentration_unit=concentration_unit)
    map_view = create_map(tif,source,grid,wind_from_deg=representative or 0.0,
        display_min_ug_m3=raster_minimum,emission_g_s=emission_value,
        wind_speed_m_s=wind.mean_speed_m_s * wind_height_factor,
        height_m=model["effective_height_m"],
        stability=model["stability"],title=config["title"],
        visualization=config.get("visualization","isolines"),
        emission_value=emission_value,emission_unit=emission_unit,
        concentration_unit=concentration_unit,contour_minimum=contour_minimum,
        contour_levels=contour_levels,wind_mode=wind.mode,
        wind_direction_std_deg=wind.direction_std_deg,wind_samples=wind.samples)
    map_view.save(str(output_dir/"mapa_pluma.html"))
    wind_rose = save_wind_rose(wind,output_dir/"rosa_vientos.png")
    isolines, contour_info = extract_isolines(tif,minimum_display=contour_minimum,
                                              levels=contour_levels)
    (output_dir/"isolineas.geojson").write_text(json.dumps(isolines,ensure_ascii=False)+"\n")
    feature = {"type":"FeatureCollection","features":[{"type":"Feature",
        "geometry":{"type":"Point","coordinates":[source.longitude_deg,source.latitude_deg]},
        "properties":{"name":config["title"],"status":s["coordinate_status"]}}]}
    (output_dir/"fuente.geojson").write_text(json.dumps(feature,ensure_ascii=False,indent=2)+"\n")
    displayed = concentration * concentration_factor_from_kg_m3(concentration_unit)
    border_max = float(max(displayed[0,:].max(),displayed[-1,:].max(),
                           displayed[:,0].max(),displayed[:,-1].max()))
    max_row,max_col = np.unravel_index(displayed.argmax(),displayed.shape)
    report={"scenario":config,"crs":source.crs.to_string(),
        "raster_file":tif.name,
        "emission_value":emission_value,"emission_unit":emission_unit,
        "emission_kg_s":q_kg_s,
        "concentration_unit":concentration_unit,
        "concentration_unit_label":unit_label(concentration_unit),
        "wind_mode":wind.mode,"wind_description":wind.description,
        "wind_samples":wind.samples,
        "wind_calculation_classes":calculation_wind.samples,
        "wind_random_seed":wind.random_seed,
        "wind_source_file":wind.source_file,"wind_rose_file":wind_rose.name,
        "wind_mean_speed_m_s":wind.mean_speed_m_s,
        "wind_reference_height_m":wind_reference_height,
        "wind_exposure":wind_exposure,
        "wind_height_factor":wind_height_factor,
        "wind_model_mean_speed_m_s":wind.mean_speed_m_s * wind_height_factor,
        "wind_representative_from_deg":wind.representative_from_deg,
        "wind_direction_std_deg":wind.direction_std_deg,
        "wind_direction_resultant_length":wind.resultant_length,
        "visualization":config.get("visualization","isolines"),
        "contour_levels":contour_info["levels"],
        "contour_level_policy":contour_info["level_policy"],
        "lowest_contour":contour_info["lowest_contour"],
        "source_easting_m":source.easting_m,"source_northing_m":source.northing_m,
        "source_longitude_deg":source.longitude_deg,"source_latitude_deg":source.latitude_deg,
        "source_input_crs":source.input_crs.to_string(),
        "source_input_x":source.input_x,"source_input_y":source.input_y,
        "meridian_convergence_deg":source.convergence_deg,"shape_rows_cols":grid.shape,
        "bounds_west_south_east_north_m":grid.bounds,"minimum_concentration":float(displayed.min()),
        "maximum_concentration":float(displayed.max()),"maximum_pixel_easting_m":float(grid.east_centres_m[max_col]),
        "maximum_pixel_northing_m":float(grid.north_centres_m[max_row]),
        "border_maximum_concentration":border_max,
        "visible_plume_reaches_domain_edge":bool(border_max>=raster_minimum),
        "sample":"pixel centres; north-to-south rows; all zeros retained"}
    if concentration_unit == "ug/m3":
        report.update(contour_levels_ug_m3=contour_info["levels"],
            lowest_contour_ug_m3=contour_info["lowest_contour"],
            minimum_ug_m3=float(displayed.min()),maximum_ug_m3=float(displayed.max()),
            border_maximum_ug_m3=border_max)
    (output_dir/"caso_y_resultados.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return map_view, report


if __name__ == "__main__":
    case_path = Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/"examples/patache.json"
    _, report=run_case(json.loads(case_path.read_text()),ROOT/"outputs"/case_path.stem)
    print(json.dumps(report,ensure_ascii=False,indent=2))
