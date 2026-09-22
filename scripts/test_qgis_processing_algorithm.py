"""Run the first plugin algorithm through QGIS Processing and verify Patache."""
from pathlib import Path
import csv
import json
import os
import sys
import tempfile
from unittest.mock import patch

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PARENT = Path(os.environ.get("GAUSSIAN_QGIS_PLUGIN_PARENT",
                                    str(ROOT / "qgis_plugin")))
sys.path.insert(0, str(PLUGIN_PARENT))


def main():
    import numpy as np
    contents = configure_macos_qgis_bundle()
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(
        Path(tempfile.gettempdir()) / "gaussian-qgis-processing-profile")
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor
    from osgeo import gdal
    from qgis.core import (QgsApplication, QgsMapRendererParallelJob,
                           QgsMapSettings, QgsProcessingException,
                           QgsProcessingFeedback, QgsProject,
                           QgsRasterLayer, QgsVectorLayer)

    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
    translation_patch = patch("gaussian_educativo.i18n.language", return_value="es")
    translation_patch.start()
    try:
        plugins = contents / "Resources/python/plugins" if contents else None
        if contents and (contents / "Resources/qgis/python/plugins").is_dir():
            plugins = contents / "Resources/qgis/python/plugins"
        if plugins and str(plugins) not in sys.path:
            sys.path.insert(0, str(plugins))
        from processing.core.Processing import Processing
        import processing
        from gaussian_educativo.provider import GaussianProvider

        Processing.initialize()
        provider = GaussianProvider()
        if not QgsApplication.processingRegistry().addProvider(provider):
            raise RuntimeError("Could not register Gaussian Processing provider")
        try:
            algorithm_id = "gaussian_educativo:simular_pluma"
            output_dir = ROOT / "outputs/qgis_plugin"
            output_dir.mkdir(parents=True, exist_ok=True)
            output = str(output_dir / "concentracion.tif")
            isoline_output = str(output_dir / "isolineas.gpkg")
            source_output = str(output_dir / "fuente.gpkg")
            for vector_path in (isoline_output, source_output):
                Path(vector_path).unlink(missing_ok=True)
            feedback = QgsProcessingFeedback()
            parameters = {
                "SOURCE": "-70.193195,-20.805320 [EPSG:4326]",
                "EMISSION": 40.0,
                "EMISSION_UNIT": 1,
                "WIND_SPEED": 5.0,
                "WIND_FROM": 0.0,
                "EFFECTIVE_HEIGHT": 50.0,
                "STABILITY": 3,
                "WIND_REFERENCE_HEIGHT": 10.0,
                "WIND_EXPOSURE": 0,
                "WIDTH": 10000.0,
                "HEIGHT": 10000.0,
                "RESOLUTION": 50.0,
                "DOMAIN_POLICY": 0,
                "CONCENTRATION_UNIT": 3,
                "CONTOUR_MODE": 0,
                "CONTOUR_MINIMUM": 1.0,
                "OUTPUT": output,
                "ISOLINES": isoline_output,
                "SOURCE_OUTPUT": source_output,
            }
            result = processing.run(algorithm_id, parameters, feedback=feedback)

            masters_paths = {
                "OUTPUT": str(output_dir / "concentracion_masters.tif"),
                "ISOLINES": str(output_dir / "isolineas_masters.gpkg"),
                "SOURCE_OUTPUT": str(output_dir / "fuente_masters.gpkg"),
            }
            for vector_path in (masters_paths["ISOLINES"],
                                masters_paths["SOURCE_OUTPUT"]):
                Path(vector_path).unlink(missing_ok=True)
            masters_parameters = dict(parameters)
            masters_parameters.update(masters_paths)
            masters_parameters.update({
                "WIND_REFERENCE_HEIGHT": 10.0,
                "WIND_EXPOSURE": 0,
                "WIDTH": 1000.0,
                "HEIGHT": 1000.0,
                "RESOLUTION": 10.0,
            })
            masters_result = processing.run(
                algorithm_id, masters_parameters,
                feedback=QgsProcessingFeedback())

            auto_paths = {
                "OUTPUT": str(output_dir / "concentracion_extendida.tif"),
                "ISOLINES": str(output_dir / "isolineas_extendidas.gpkg"),
                "SOURCE_OUTPUT": str(output_dir / "fuente_extendida.gpkg"),
            }
            for vector_path in (auto_paths["ISOLINES"],
                                auto_paths["SOURCE_OUTPUT"]):
                Path(vector_path).unlink(missing_ok=True)
            auto_parameters = dict(parameters)
            auto_parameters.update(auto_paths)
            auto_parameters["DOMAIN_POLICY"] = 1
            auto_result = processing.run(
                algorithm_id, auto_parameters,
                feedback=QgsProcessingFeedback())

            csv_paths = {
                "OUTPUT": str(output_dir / "concentracion_viento_csv.tif"),
                "ISOLINES": str(output_dir / "isolineas_viento_csv.gpkg"),
                "SOURCE_OUTPUT": str(output_dir / "fuente_viento_csv.gpkg"),
                "WIND_ROSE": str(output_dir / "rosa_vientos_csv.png"),
            }
            for vector_path in (csv_paths["ISOLINES"],
                                csv_paths["SOURCE_OUTPUT"]):
                Path(vector_path).unlink(missing_ok=True)
            csv_parameters = dict(parameters)
            csv_parameters.update(csv_paths)
            csv_parameters["WIND_MODE"] = 3
            csv_parameters["EMISSION"] = 100.0
            csv_parameters["STABILITY"] = 0
            source_wind_path = ROOT / "examples/synthetic_ne_sw_wind.csv"
            categorized_wind_path = output_dir / "wind_with_categories.csv"
            with source_wind_path.open(newline="", encoding="utf-8") as source_stream:
                source_rows = list(csv.DictReader(source_stream))
            with categorized_wind_path.open(
                    "w", newline="", encoding="utf-8") as target_stream:
                fields = list(source_rows[0]) + [
                    "source_total_rows", "excluded_calm_rows",
                    "excluded_variable_rows", "excluded_missing_rows"]
                writer = csv.DictWriter(target_stream, fieldnames=fields)
                writer.writeheader()
                for source_row in source_rows:
                    writer.writerow({**source_row, "source_total_rows": 1230,
                                     "excluded_calm_rows": 10,
                                     "excluded_variable_rows": 15,
                                     "excluded_missing_rows": 5})
            csv_parameters["WIND_FILE"] = str(categorized_wind_path)
            csv_parameters["DOMAIN_POLICY"] = 0
            csv_result = processing.run(
                algorithm_id, csv_parameters,
                feedback=QgsProcessingFeedback())
            synthetic_results = {}
            for mode_index, mode_name in ((1, "prevailing"),
                                          (2, "fluctuating")):
                synthetic_parameters = dict(parameters)
                synthetic_parameters.update({
                    "WIND_MODE": mode_index,
                    "WIND_FROM": 225.0,
                    "WIDTH": 1000.0,
                    "HEIGHT": 1000.0,
                    "RESOLUTION": 100.0,
                    "OUTPUT": str(output_dir / ("concentracion_" + mode_name + ".tif")),
                    "ISOLINES": "TEMPORARY_OUTPUT",
                    "SOURCE_OUTPUT": "TEMPORARY_OUTPUT",
                })
                synthetic_results[mode_name] = processing.run(
                    algorithm_id, synthetic_parameters,
                    feedback=QgsProcessingFeedback())
            excessive_parameters = dict(parameters)
            excessive_parameters.update({
                "WIND_MODE": 1, "RESOLUTION": 10.0,
                "OUTPUT": "TEMPORARY_OUTPUT",
                "ISOLINES": "TEMPORARY_OUTPUT",
                "SOURCE_OUTPUT": "TEMPORARY_OUTPUT",
            })
            try:
                processing.run(algorithm_id, excessive_parameters,
                               feedback=QgsProcessingFeedback())
                excessive_work_rejected = False
                excessive_work_error = ""
            except QgsProcessingException as error:
                excessive_work_error = str(error)
                excessive_work_rejected = (
                    "52,000,000" in excessive_work_error and
                    "20 m" in excessive_work_error)
            limited_extension_parameters = dict(parameters)
            limited_extension_parameters.update({
                "WIND_MODE": 1,
                "WIND_FROM": 0.0,
                "STABILITY": 0,
                "RESOLUTION": 50.0,
                "DOMAIN_POLICY": 1,
                "OUTPUT": "TEMPORARY_OUTPUT",
                "ISOLINES": "TEMPORARY_OUTPUT",
                "SOURCE_OUTPUT": "TEMPORARY_OUTPUT",
            })
            limited_extension_result = processing.run(
                algorithm_id, limited_extension_parameters,
                feedback=QgsProcessingFeedback())
        finally:
            QgsApplication.processingRegistry().removeProvider(provider)

        dataset = gdal.Open(result["OUTPUT"])
        if dataset is None:
            raise RuntimeError("Processing did not create the output raster")
        band = dataset.GetRasterBand(1)
        values = band.ReadAsArray()
        projection = dataset.GetProjection()
        raster_metadata = dataset.GetMetadata()
        masters_dataset = gdal.Open(masters_result["OUTPUT"])
        masters_band = masters_dataset.GetRasterBand(1)
        masters_values = masters_band.ReadAsArray()
        masters_metadata = masters_dataset.GetMetadata()
        isolines = QgsVectorLayer(result["ISOLINES"], "isolines", "ogr")
        source = QgsVectorLayer(result["SOURCE_OUTPUT"], "source", "ogr")
        levels = sorted(set(float(feature["concentration"])
                            for feature in isolines.getFeatures()))
        source_feature = next(source.getFeatures())
        source_point = source_feature.geometry().asPoint()
        from gaussian_educativo.styles import (style_isolines, style_raster,
                                                style_source)
        raster_layer = QgsRasterLayer(result["OUTPUT"], "raster")
        style_raster(raster_layer, levels, result["MAXIMUM"], 0.1, "µg/m³")
        style_isolines(isolines, levels, "µg/m³")
        style_source(source)
        project = QgsProject.instance()
        project.clear()
        project.setCrs(raster_layer.crs())
        for layer in (raster_layer, isolines, source):
            project.addMapLayer(layer)
        project_path = output_dir / "proyecto_mvp_040_fijo.qgz"
        if not project.write(str(project_path)):
            raise RuntimeError("QGIS could not write the plugin preview project")
        settings = QgsMapSettings()
        settings.setLayers([source, isolines, raster_layer])
        settings.setDestinationCrs(raster_layer.crs())
        settings.setExtent(raster_layer.extent())
        settings.setOutputSize(QSize(900, 900))
        settings.setBackgroundColor(QColor("white"))
        render = QgsMapRendererParallelJob(settings)
        render.start()
        render.waitForFinished()
        preview_path = output_dir / "vista_mvp_040_fijo.png"
        if not render.renderedImage().save(str(preview_path)):
            raise RuntimeError("QGIS could not write the plugin preview")
        fixed_layer_report = {
            "isoline_crs": isolines.crs().authid(),
            "isoline_feature_count": isolines.featureCount(),
            "source_crs": source.crs().authid(),
            "source_feature_count": source.featureCount(),
            "styles": {
                "raster": type(raster_layer.renderer()).__name__,
                "isolines": type(isolines.renderer()).__name__,
                "labels_enabled": isolines.labelsEnabled(),
                "source": type(source.renderer().symbol().symbolLayer(0)).__name__,
            },
        }

        auto_raster = QgsRasterLayer(auto_result["OUTPUT"], "raster extendido")
        auto_isolines = QgsVectorLayer(auto_result["ISOLINES"],
                                       "isolíneas extendidas", "ogr")
        auto_source = QgsVectorLayer(auto_result["SOURCE_OUTPUT"],
                                     "fuente extendida", "ogr")
        auto_levels = sorted(set(float(feature["concentration"])
                                 for feature in auto_isolines.getFeatures()))
        style_raster(auto_raster, auto_levels, auto_result["MAXIMUM"],
                     0.1, "µg/m³")
        style_isolines(auto_isolines, auto_levels, "µg/m³")
        style_source(auto_source)
        project.clear()
        project.setCrs(auto_raster.crs())
        for layer in (auto_raster, auto_isolines, auto_source):
            project.addMapLayer(layer)
        auto_project_path = output_dir / "proyecto_mvp_040_extendido.qgz"
        if not project.write(str(auto_project_path)):
            raise RuntimeError("QGIS could not write the extended project")
        auto_settings = QgsMapSettings()
        auto_settings.setLayers([auto_source, auto_isolines, auto_raster])
        auto_settings.setDestinationCrs(auto_raster.crs())
        auto_settings.setExtent(auto_raster.extent())
        auto_settings.setOutputSize(QSize(900, 900))
        auto_settings.setBackgroundColor(QColor("white"))
        auto_render = QgsMapRendererParallelJob(auto_settings)
        auto_render.start()
        auto_render.waitForFinished()
        auto_preview_path = output_dir / "vista_mvp_040_extendido.png"
        if not auto_render.renderedImage().save(str(auto_preview_path)):
            raise RuntimeError("QGIS could not write the extended preview")

        csv_raster = QgsRasterLayer(csv_result["OUTPUT"], "ráster viento CSV")
        csv_isolines = QgsVectorLayer(csv_result["ISOLINES"],
                                      "isolíneas viento CSV", "ogr")
        csv_source = QgsVectorLayer(csv_result["SOURCE_OUTPUT"],
                                    "fuente viento CSV", "ogr")
        csv_levels = sorted(set(float(feature["concentration"])
                                for feature in csv_isolines.getFeatures()))
        style_raster(csv_raster, csv_levels, csv_result["MAXIMUM"],
                     0.1, "µg/m³")
        style_isolines(csv_isolines, csv_levels, "µg/m³")
        style_source(csv_source)
        project.clear()
        project.setCrs(csv_raster.crs())
        for layer in (csv_raster, csv_isolines, csv_source):
            project.addMapLayer(layer)
        csv_project_path = output_dir / "proyecto_mvp_040_viento_csv.qgz"
        if not project.write(str(csv_project_path)):
            raise RuntimeError("QGIS could not write the wind CSV project")
        csv_settings = QgsMapSettings()
        csv_settings.setLayers([csv_source, csv_isolines, csv_raster])
        csv_settings.setDestinationCrs(csv_raster.crs())
        csv_settings.setExtent(csv_raster.extent())
        csv_settings.setOutputSize(QSize(900, 900))
        csv_settings.setBackgroundColor(QColor("white"))
        csv_render = QgsMapRendererParallelJob(csv_settings)
        csv_render.start()
        csv_render.waitForFinished()
        csv_preview_path = output_dir / "vista_mvp_040_viento_csv.png"
        if not csv_render.renderedImage().save(str(csv_preview_path)):
            raise RuntimeError("QGIS could not write the wind CSV preview")
        csv_metadata = gdal.Open(csv_result["OUTPUT"]).GetMetadata()
        result_report = {
            "status": "passed",
            "algorithm": algorithm_id,
            "output": result["OUTPUT"],
            "output_crs": result["OUTPUT_CRS"],
            "shape_rows_cols": [dataset.RasterYSize, dataset.RasterXSize],
            "maximum": result["MAXIMUM"],
            "maximum_from_raster": float(values.max()),
            "border_maximum": result["BORDER_MAXIMUM"],
            "nodata": band.GetNoDataValue(),
            "unit": band.GetMetadataItem("units"),
            "has_utm_19s_projection": "UTM zone 19S" in projection,
            "raster_domain_metadata": {
                key: raster_metadata.get(key) for key in
                ("domain_policy", "domain_status", "domain_iterations",
                 "domain_width_m", "domain_height_m",
                 "edge_concentration_unit", "wind_calculation_classes")
            },
            "isoline_crs": fixed_layer_report["isoline_crs"],
            "isoline_levels": levels,
            "isoline_feature_count": fixed_layer_report["isoline_feature_count"],
            "source_crs": fixed_layer_report["source_crs"],
            "source_feature_count": fixed_layer_report["source_feature_count"],
            "source_easting_northing": [source_point.x(), source_point.y()],
            "styles": fixed_layer_report["styles"],
            "project": str(project_path),
            "preview": str(preview_path),
            "feedback_mentions_truncation":
                "resultado como truncado" in feedback.textLog().lower(),
            "synthetic_wind": {
                "prevailing_samples": synthetic_results["prevailing"]["WIND_SAMPLES"],
                "prevailing_from_deg": synthetic_results["prevailing"]["REPRESENTATIVE_WIND_FROM"],
                "fluctuating_samples": synthetic_results["fluctuating"]["WIND_SAMPLES"],
                "fluctuating_from_deg": synthetic_results["fluctuating"]["REPRESENTATIVE_WIND_FROM"],
            },
            "excessive_work_rejected": excessive_work_rejected,
            "excessive_work_error": excessive_work_error,
            "limited_synthetic_extension": {
                "status": limited_extension_result["DOMAIN_STATUS"],
                "iterations": limited_extension_result["DOMAIN_ITERATIONS"],
                "samples": limited_extension_result["WIND_SAMPLES"],
                "width_m": limited_extension_result["ACTUAL_WIDTH"],
                "height_m": limited_extension_result["ACTUAL_HEIGHT"],
                "output_exists": Path(
                    limited_extension_result["OUTPUT"]).is_file(),
            },
            "domain": {
                "status": result["DOMAIN_STATUS"],
                "iterations": result["DOMAIN_ITERATIONS"],
                "width_m": result["ACTUAL_WIDTH"],
                "height_m": result["ACTUAL_HEIGHT"],
                "north": result["BORDER_NORTH"],
                "south": result["BORDER_SOUTH"],
                "west": result["BORDER_WEST"],
                "east": result["BORDER_EAST"],
            },
            "automatic_extension": {
                "status": auto_result["DOMAIN_STATUS"],
                "iterations": auto_result["DOMAIN_ITERATIONS"],
                "width_m": auto_result["ACTUAL_WIDTH"],
                "height_m": auto_result["ACTUAL_HEIGHT"],
                "maximum": auto_result["MAXIMUM"],
                "border_maximum": auto_result["BORDER_MAXIMUM"],
                "project": str(auto_project_path),
                "preview": str(auto_preview_path),
            },
            "wind_csv": {
                "samples": csv_result["WIND_SAMPLES"],
                "mean_speed_m_s": csv_result["MEAN_WIND_SPEED"],
                "representative_from_deg":
                    csv_result["REPRESENTATIVE_WIND_FROM"],
                "maximum": csv_result["MAXIMUM"],
                "border_maximum": csv_result["BORDER_MAXIMUM"],
                "domain_status": csv_result["DOMAIN_STATUS"],
                "rose": csv_result["WIND_ROSE"],
                "rose_is_png": Path(csv_result["WIND_ROSE"]).read_bytes()[:8] ==
                    b"\x89PNG\r\n\x1a\n",
                "calculation_classes": int(gdal.Open(
                    csv_result["OUTPUT"]).GetMetadataItem(
                        "wind_calculation_classes")),
                "source_counts": {
                    key: csv_metadata.get(key) for key in
                    ("wind_source_total_rows", "wind_excluded_calm_rows",
                     "wind_excluded_variable_rows", "wind_excluded_missing_rows",
                     "wind_concentration_basis")
                },
                "project": str(csv_project_path),
                "preview": str(csv_preview_path),
            },
            "masters": {
                "maximum": masters_result["MAXIMUM"],
                "nodata_cells": int(np.count_nonzero(
                    masters_values == masters_band.GetNoDataValue())),
                "dispersion_model":
                    masters_metadata.get("dispersion_model"),
                "wind_reference_height_m":
                    masters_metadata.get("wind_reference_height_m"),
                "wind_height_factor":
                    float(masters_metadata.get("wind_height_factor")),
                "near_source_nodata_radius_m":
                    masters_metadata.get("near_source_nodata_radius_m"),
            },
        }
        checks = [
            result_report["output_crs"] == "EPSG:32719",
            result_report["shape_rows_cols"] == [200, 200],
            abs(result_report["maximum"] - 221.55702842230076) < 1e-9,
            abs(result_report["maximum_from_raster"] - result_report["maximum"]) < 1e-12,
            abs(result_report["border_maximum"] - 57.27933701364513) < 1e-9,
            result_report["nodata"] == -9999.0,
            result_report["unit"] == "ug/m3",
            result_report["masters"]["maximum"] > 0,
            result_report["masters"]["nodata_cells"] == 12,
            result_report["masters"]["dispersion_model"] ==
                "masters_2008_martin_1976",
            result_report["masters"]["wind_reference_height_m"] == "10.0",
            abs(result_report["masters"]["wind_height_factor"] -
                (50 / 10) ** .25) < 1e-12,
            abs(float(result_report["masters"]["near_source_nodata_radius_m"])
                - 16.5859017) < 1e-6,
            result_report["has_utm_19s_projection"],
            result_report["raster_domain_metadata"] == {
                "domain_policy": "fixed",
                "domain_status": "fixed_truncated",
                "domain_iterations": "0",
                "domain_width_m": "10000.0",
                "domain_height_m": "10000.0",
                "edge_concentration_unit": "ug/m3",
                "wind_calculation_classes": "1",
            },
            result_report["isoline_crs"] == "EPSG:32719",
            result_report["isoline_levels"] ==
                [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0],
            result_report["isoline_feature_count"] >= len(levels),
            result_report["source_crs"] == "EPSG:32719",
            result_report["source_feature_count"] == 1,
            abs(result_report["source_easting_northing"][0] - 375825.81901894213) < 1e-6,
            abs(result_report["source_easting_northing"][1] - 7698938.582415143) < 1e-6,
            result_report["styles"] == {
                "raster": "QgsSingleBandPseudoColorRenderer",
                "isolines": "QgsCategorizedSymbolRenderer",
                "labels_enabled": True,
                "source": "QgsSvgMarkerSymbolLayer",
            },
            result_report["feedback_mentions_truncation"],
            result_report["synthetic_wind"] == {
                "prevailing_samples": 1200,
                "prevailing_from_deg": 225.0,
                "fluctuating_samples": 1200,
                "fluctuating_from_deg": -1.0,
            },
            result_report["excessive_work_rejected"],
            result_report["limited_synthetic_extension"] == {
                "status": "extended_edge_criteria_met",
                "iterations": 0,
                "samples": 1200,
                "width_m": 10000.0,
                "height_m": 10000.0,
                "output_exists": True,
            },
            result_report["domain"]["status"] == "fixed_truncated",
            result_report["domain"]["iterations"] == 0,
            result_report["domain"]["width_m"] == 10000.0,
            result_report["domain"]["height_m"] == 10000.0,
            abs(result_report["domain"]["south"] -
                result_report["border_maximum"]) < 1e-12,
            result_report["automatic_extension"]["status"] ==
                "safety_limit_reached_truncated",
            result_report["automatic_extension"]["iterations"] == 4,
            result_report["automatic_extension"]["width_m"] == 15000.0,
            result_report["automatic_extension"]["height_m"] == 85000.0,
            abs(result_report["automatic_extension"]["maximum"] -
                result_report["maximum"]) < 1e-12,
            result_report["automatic_extension"]["border_maximum"] <
                result_report["border_maximum"],
            result_report["wind_csv"]["samples"] == 1200,
            abs(result_report["wind_csv"]["representative_from_deg"] -
                44.82549413630073) < 1e-9,
            abs(result_report["wind_csv"]["maximum"] -
                754.5445318479478) < 1e-9,
            abs(result_report["wind_csv"]["border_maximum"] -
                0.14091021176519675) < 1e-9,
            result_report["wind_csv"]["domain_status"] == "fixed_truncated",
            result_report["wind_csv"]["calculation_classes"] == 59,
            result_report["wind_csv"]["source_counts"] == {
                "wind_source_total_rows": "1230",
                "wind_excluded_calm_rows": "10",
                "wind_excluded_variable_rows": "15",
                "wind_excluded_missing_rows": "5",
                "wind_concentration_basis":
                    "directional observations with positive speed; conditional weights sum to 1",
            },
            result_report["wind_csv"]["rose_is_png"],
        ]
        if not all(checks):
            result_report["status"] = "failed"
        dataset = None
        project.clear()
        render = None
        auto_render = None
        csv_render = None
        raster_layer = None
        isolines = None
        source = None
        auto_raster = None
        auto_isolines = None
        auto_source = None
        csv_raster = None
        csv_isolines = None
        csv_source = None
    finally:
        translation_patch.stop()
        app.exitQgis()

    report_path = ROOT / "validation/qgis_processing_algorithm.json"
    report_path.write_text(json.dumps(result_report, indent=2) + "\n")
    print(json.dumps(result_report, indent=2))
    return 0 if result_report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
