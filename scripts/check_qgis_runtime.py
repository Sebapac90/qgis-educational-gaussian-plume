"""Headless compatibility check for the Python runtime bundled with QGIS.

Run this script with QGIS's Python executable. On macOS it derives the bundled
GDAL/PROJ paths for this process only; it does not change the user's shell or
global environment.
"""
from pathlib import Path
import csv
import importlib.util
import json
import os
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure_macos_qgis_bundle():
    executable = Path(sys.executable).resolve()
    contents = next((parent for parent in executable.parents
                     if parent.name == "Contents"), None)
    if contents is None:
        return None
    resources = contents / "Resources"
    if (resources / "qgis/proj/proj.db").is_file():
        resources = resources / "qgis"
    os.environ["PROJ_LIB"] = str(resources / "proj")
    os.environ["PROJ_DATA"] = str(resources / "proj")
    os.environ["GDAL_DATA"] = str(resources / "gdal")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/gaussian-qgis-mpl")
    return contents


def configure_application(app, contents):
    """Set paths for both classic and current official macOS app layouts."""
    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    if contents and (contents / "Resources/qgis/proj/proj.db").is_file():
        prefix = contents / "Resources/qgis"
    app.setPrefixPath(str(prefix), True)
    if contents and (contents / "PlugIns/qgis").is_dir():
        app.setPluginPath(str(contents / "PlugIns/qgis"))


def main():
    contents = configure_macos_qgis_bundle()

    import numpy as np
    from osgeo import gdal, osr
    from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform, QgsPointXY, QgsProject)
    from gaussian_core import gaussian_concentration
    from gaussian_spatial import locate_source_coordinates
    from gaussian_wind import wind_from_config

    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
    try:
        rows = list(csv.DictReader((ROOT / "validation/centreline_cases.csv").open()))
        relative_errors = []
        for row in rows:
            actual = float(gaussian_concentration(
                float(row["x_downwind_m"]), float(row["y_crosswind_m"]),
                float(row["z_m"]), emission_kg_s=float(row["emission_kg_s"]),
                wind_speed_m_s=float(row["wind_speed_m_s"]),
                effective_height_m=float(row["height_m"]),
                stability=row["stability"]))
            expected = float(row["expected_kg_m3"])
            relative_errors.append(abs(actual - expected) / expected)

        source = locate_source_coordinates(-70.193195, -20.805320,
                                           input_crs="EPSG:4326")
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsCoordinateReferenceSystem("EPSG:32719"),
            QgsProject.instance())
        qgis_point = transform.transform(QgsPointXY(-70.193195, -20.805320))

        wind = wind_from_config({"wind_mode": "table",
            "wind_file": "examples/synthetic_ne_sw_wind.csv"}, base_dir=ROOT)

        raster_path = "/vsimem/gaussian_qgis_runtime.tif"
        raster = gdal.GetDriverByName("GTiff").Create(raster_path, 2, 2, 1,
                                                       gdal.GDT_Float64)
        raster.SetGeoTransform((source.easting_m - 50, 50, 0,
                                source.northing_m + 50, 0, -50))
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(32719)
        raster.SetProjection(spatial_reference.ExportToWkt())
        expected_pixels = np.array([[0., 1.], [2., 3.]], dtype=float)
        raster.GetRasterBand(1).WriteArray(expected_pixels)
        raster.FlushCache()
        raster = None
        opened = gdal.Open(raster_path)
        actual_pixels = opened.GetRasterBand(1).ReadAsArray()
        raster_ok = bool(np.array_equal(actual_pixels, expected_pixels))
        opened = None
        gdal.Unlink(raster_path)

        optional = {name: importlib.util.find_spec(name) is not None for name in
                    ("pyproj", "rasterio", "matplotlib", "folium", "attrs")}
        report = {
            "status": "compatible_for_minimum_plugin" if raster_ok else "failed",
            "qgis": Qgis.QGIS_VERSION,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "gdal": gdal.VersionInfo("RELEASE_NAME"),
            "proj": osr.GetPROJVersionMajor().__str__() + "." +
                    osr.GetPROJVersionMinor().__str__(),
            "core_cases_compared": len(rows),
            "core_max_relative_error": max(relative_errors),
            "calculation_crs": source.crs.to_string(),
            "pyproj_utm": [source.easting_m, source.northing_m],
            "qgis_utm": [qgis_point.x(), qgis_point.y()],
            "coordinate_max_difference_m": max(
                abs(source.easting_m - qgis_point.x()),
                abs(source.northing_m - qgis_point.y())),
            "wind_table_rows": wind.samples,
            "native_gdal_raster_round_trip": raster_ok,
            "optional_modules": optional,
            "decision": "Use QGIS/GDAL APIs in the plugin; keep Folium browser-only",
        }
    finally:
        app.exitQgis()

    output = ROOT / "validation/qgis_runtime.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "compatible_for_minimum_plugin" else 1


if __name__ == "__main__":
    sys.exit(main())
