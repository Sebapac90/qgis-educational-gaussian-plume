"""Run a Briggs scenario through the real QGIS Processing provider."""
from pathlib import Path
import json
import os
import sys
import tempfile

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qgis_plugin"))


def main():
    contents = configure_macos_qgis_bundle()
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(
        Path(tempfile.gettempdir()) / "gaussian-qgis-briggs-profile")
    from osgeo import gdal
    from qgis.core import QgsApplication, QgsProcessingFeedback

    prefix = (contents / "MacOS" if contents else
              Path(os.environ["QGIS_PREFIX_PATH"]))
    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
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
        QgsApplication.processingRegistry().addProvider(provider)
        try:
            output = ROOT / "outputs/qgis_plugin/concentracion_briggs.tif"
            result = processing.run(
                "gaussian_educativo:simular_pluma", {
                    "SOURCE": "-70.193195,-20.805320 [EPSG:4326]",
                    "EMISSION": 40., "EMISSION_UNIT": 1,
                    "WIND_MODE": 0, "WIND_SPEED": 5., "WIND_FROM": 0.,
                    "EFFECTIVE_HEIGHT": 50., "HEIGHT_MODE": 2,
                    "STACK_DIAMETER": 2., "EXIT_VELOCITY": 10.,
                    "STACK_TEMPERATURE_C": 126.85,
                    "AMBIENT_TEMPERATURE_C": 26.85,
                    "AMBIENT_GRADIENT_C_KM": 2.,
                    "STACK_TIP_DOWNWASH": 0, "STABILITY": 3,
                    "WIND_REFERENCE_HEIGHT": 10., "WIND_EXPOSURE": 0,
                    "WIDTH": 2000., "HEIGHT": 2000., "RESOLUTION": 50.,
                    "DOMAIN_POLICY": 0, "CONCENTRATION_UNIT": 3,
                    "CONTOUR_MODE": 0, "CONTOUR_MINIMUM": 1.,
                    "OUTPUT": str(output),
                    "ISOLINES": "TEMPORARY_OUTPUT",
                    "SOURCE_OUTPUT": "TEMPORARY_OUTPUT",
                }, feedback=QgsProcessingFeedback())
        finally:
            QgsApplication.processingRegistry().removeProvider(provider)
        dataset = gdal.Open(result["OUTPUT"])
        metadata = dataset.GetMetadata()
        report = {
            "status": "passed",
            "qgis_prefix": str(prefix),
            "maximum_ug_m3": result["MAXIMUM"],
            "height_mode": metadata.get("height_mode"),
            "stack_height_m": metadata.get("stack_height_m"),
            "plume_rise_m": metadata.get("plume_rise_m"),
            "effective_height_m": metadata.get("effective_height_m"),
            "stack_temperature_k": metadata.get(
                "briggs_stack_temperature_k"),
        }
        checks = [
            report["maximum_ug_m3"] > 0,
            report["height_mode"] == "briggs",
            abs(float(report["stack_height_m"]) - 50.) < 1e-12,
            float(report["plume_rise_m"]) > 0,
            float(report["effective_height_m"]) > 50.,
            abs(float(report["stack_temperature_k"]) - 400.) < 1e-12,
        ]
        if not all(checks):
            report["status"] = "failed"
        dataset = None
    finally:
        app.exitQgis()
    path = ROOT / "validation/qgis_briggs.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
