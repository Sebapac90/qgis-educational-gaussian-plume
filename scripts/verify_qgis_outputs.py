"""Verify the canonical outputs through QGIS and its bundled GDAL provider."""
from pathlib import Path
import json
import math
import os
import sys

from create_qgis_validation_project import configure_bundle, ROOT, OUTPUT


def close(actual, expected, tolerance):
    return math.isclose(float(actual), float(expected), rel_tol=0.0,
                        abs_tol=tolerance)


def main():
    contents = configure_bundle()
    from osgeo import gdal
    from qgis.core import (QgsApplication, QgsPointXY, QgsProject, QgsRaster,
                           QgsRasterBandStats, QgsRasterBlock, QgsRasterLayer,
                           QgsVectorLayer)

    prefix = contents / "MacOS" if contents else Path()
    app = QgsApplication([], False)
    app.setPrefixPath(str(prefix), True)
    app.initQgis()
    try:
        raster_path = OUTPUT / "pluma_ug_m3.tif"
        raster = QgsRasterLayer(str(raster_path), "Concentración")
        source = QgsVectorLayer(str(OUTPUT / "fuente.geojson"), "Fuente", "ogr")
        isolines = QgsVectorLayer(str(OUTPUT / "isolineas.geojson"),
                                  "Isolíneas", "ogr")
        expected = json.loads((OUTPUT / "caso_y_resultados.json").read_text())
        provider = raster.dataProvider()
        stats = provider.bandStatistics(1, QgsRasterBandStats.All,
                                        raster.extent(), 0)

        def value_at(easting, northing):
            identified = provider.identify(QgsPointXY(easting, northing),
                                           QgsRaster.IdentifyFormatValue)
            if not identified.isValid():
                raise RuntimeError("QGIS could not identify the raster value")
            return float(identified.results()[1])

        maximum_point = (expected["maximum_pixel_easting_m"],
                         expected["maximum_pixel_northing_m"])
        source_easting = expected["source_easting_m"]
        source_northing = expected["source_northing_m"]
        north_point = (source_easting + 25.0, raster.extent().yMaximum() - 25.0)
        south_point = (source_easting + 25.0, raster.extent().yMinimum() + 25.0)
        samples = {
            "maximum": value_at(*maximum_point),
            "north_zero": value_at(*north_point),
            "south_border": value_at(*south_point),
        }

        dataset = gdal.Open(str(raster_path))
        band = dataset.GetRasterBand(1)
        band_metadata = band.GetMetadata()
        data_type = gdal.GetDataTypeName(band.DataType)
        nodata = band.GetNoDataValue()
        band_description = band.GetDescription()
        dataset = None

        project = QgsProject.instance()
        project_ok = project.read(str(OUTPUT / "proyecto_validacion.qgz"))
        project_layers = {layer.name(): layer for layer in project.mapLayers().values()}
        isoline_values = sorted(float(feature["concentration"])
                                for feature in isolines.getFeatures())

        checks = {
            "layers_valid": raster.isValid() and source.isValid() and isolines.isValid(),
            "crs": (raster.crs().authid() == "EPSG:32719" and
                    source.crs().authid() == "EPSG:4326" and
                    isolines.crs().authid() == "EPSG:4326"),
            "shape": provider.xSize() == 200 and provider.ySize() == 200,
            "data_type": data_type == "Float64",
            "pixel_size": (close(raster.rasterUnitsPerPixelX(), 50.0, 1e-12) and
                           close(raster.rasterUnitsPerPixelY(), 50.0, 1e-12)),
            "nodata": close(nodata, -9999.0, 0.0),
            "statistics": (close(stats.minimumValue, 0.0, 1e-12) and
                           close(stats.maximumValue,
                                 expected["maximum_concentration"], 1e-9)),
            "maximum_sample": close(samples["maximum"],
                                    expected["maximum_concentration"], 1e-9),
            "north_is_valid_zero": close(samples["north_zero"], 0.0, 0.0),
            "south_border_sample": close(samples["south_border"],
                                         expected["border_maximum_concentration"], 1e-9),
            "units": band_metadata.get("units") == "ug/m3",
            "band_description": "µg/m³" in band_description,
            "isoline_levels": isoline_values == [float(v) for v in
                                                   expected["contour_levels"]],
            "project_reopens": project_ok,
            "raster_style": project_layers["Concentración (µg/m³)"].renderer().type()
                            == "singlebandpseudocolor",
            "isoline_style_and_labels": (
                project_layers["Isolíneas (µg/m³)"].renderer().type()
                == "categorizedSymbol" and
                project_layers["Isolíneas (µg/m³)"].labelsEnabled()),
        }
        report = {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "raster": {
                "crs": raster.crs().authid(),
                "shape_rows_cols": [provider.ySize(), provider.xSize()],
                "pixel_size_m": [raster.rasterUnitsPerPixelX(),
                                 raster.rasterUnitsPerPixelY()],
                "data_type": data_type,
                "nodata": nodata,
                "minimum": stats.minimumValue,
                "maximum": stats.maximumValue,
                "band_description": band_description,
                "band_metadata": band_metadata,
            },
            "samples_ug_m3": samples,
            "sample_coordinates_easting_northing": {
                "maximum": maximum_point,
                "north_zero": north_point,
                "south_border": south_point,
            },
            "isoline_levels_ug_m3": isoline_values,
        }
    finally:
        QgsProject.instance().clear()
        app.exitQgis()

    output = ROOT / "validation/qgis_layers.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    exit_code = main()
    # A loaded XYZ layer can leave a Qt network thread alive after exitQgis().
    # The report and all QGIS cleanup are complete at this point.
    sys.stdout.flush()
    os._exit(exit_code)
