"""Verify bilingual controls, catalog formatting and cross-language scenarios."""
from pathlib import Path
import json
import os
import string
import sys
import tempfile
from unittest.mock import Mock, patch

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle
from test_qgis_panel import FakeInterface

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("GAUSSIAN_QGIS_PLUGIN_PARENT", str(ROOT / "qgis_plugin")))


def main():
    contents = configure_macos_qgis_bundle()
    from qgis.PyQt.QtWidgets import QMainWindow
    from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsPointXY
    from qgis.gui import QgsMapCanvas
    from gaussian_educativo.plugin import GaussianEducationalPlugin
    from gaussian_educativo import i18n

    app = QgsApplication([], False)
    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    configure_application(app, contents)
    app.initQgis()
    records = []
    try:
        formatter = string.Formatter()
        placeholders = lambda text: [(name, spec, conversion) for _, name, spec, conversion
                                     in formatter.parse(text) if name is not None]
        catalog = i18n.english_catalog()
        formats_match = all(placeholders(source) == placeholders(target)
                            for source, target in catalog.items())
        with tempfile.TemporaryDirectory(prefix="gaussian-languages-") as directory:
            scenario = Path(directory) / "scenario.json"
            original = None
            for locale, expected in [("es_CL", "Ejecutar y cargar capas"),
                                     ("en_US", "Run and load layers"),
                                     ("fr_FR", "Run and load layers")]:
                settings = Mock()
                settings.value.side_effect = lambda key, default=None, **kw: {
                    "locale/overrideFlag": True, "locale/userLocale": locale}.get(key, default)
                with patch.object(i18n, "QgsSettings", return_value=settings):
                    canvas = QgsMapCanvas()
                    window = QMainWindow()
                    window.resize(650, 850)
                    interface = FakeInterface(canvas, window)
                    plugin = GaussianEducationalPlugin(interface)
                    plugin.initGui()
                    dock = plugin.dock
                    if original is None:
                        dock.set_source(QgsPointXY(-70.193195, -20.805320),
                                        QgsCoordinateReferenceSystem("EPSG:4326"))
                        dock.output_dir_edit.setText(directory)
                        dock.scenario_edit.setText("Caso bilingüe")
                        dock.save_scenario(scenario)
                        original = dock.algorithm_parameters()
                    else:
                        dock.load_scenario(scenario)
                    algorithm = QgsApplication.processingRegistry().algorithmById(dock.ALGORITHM_ID)
                    record = {"locale": locale, "language": i18n.language(),
                              "run_button": dock.run_button.text(),
                              "algorithm_name": algorithm.displayName(),
                              "scenario_inputs_match": dock.algorithm_parameters() == original}
                    record["passed"] = (record["run_button"] == expected and
                                        record["scenario_inputs_match"] and
                                        algorithm.parameterDefinition("EMISSION").description() ==
                                        ("Emisión" if i18n.language() == "es" else "Emission"))
                    plugin.show_dock()
                    window.show()
                    app.processEvents()
                    if locale != "fr_FR":
                        screenshot = ROOT / "validation" / ("panel_" + i18n.language() + "_090.png")
                        record["screenshot_saved"] = window.grab().save(str(screenshot), "PNG")
                        record["passed"] = record["passed"] and record["screenshot_saved"]
                    plugin.unload()
                    record["clean_unload"] = not interface.actions and not interface.docks
                    record["passed"] = record["passed"] and record["clean_unload"]
                    records.append(record)
                    window.close()
    finally:
        app.exitQgis()
    report = {"status": "passed" if formats_match and all(r["passed"] for r in records)
              else "failed", "catalog_entries": len(catalog),
              "format_placeholders_match": formats_match, "locales": records}
    (ROOT / "validation/qgis_languages.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
