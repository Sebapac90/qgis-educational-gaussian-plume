"""Stress the multi-source automatic-domain workflow in real QGIS tasks."""
from pathlib import Path
import json
import os
import sys
import tempfile
from unittest.mock import patch

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PARENT = Path(os.environ.get(
    "GAUSSIAN_QGIS_PLUGIN_PARENT", str(ROOT / "qgis_plugin")))
sys.path.insert(0, str(PLUGIN_PARENT))


class FakeInterface:
    def __init__(self, canvas, window):
        self.canvas = canvas
        self.window = window

    def mapCanvas(self):
        return self.canvas

    def mainWindow(self):
        return self.window

    def addPluginToMenu(self, *args):
        pass

    def removePluginMenu(self, *args):
        pass

    def addToolBarIcon(self, *args):
        pass

    def removeToolBarIcon(self, *args):
        pass

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


def main():
    contents = configure_macos_qgis_bundle()
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(
        Path(tempfile.gettempdir()) / "gaussian-qgis-multisource-stress")
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtWidgets import QMainWindow
    from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
                           QgsPointXY, QgsProject, QgsRectangle)
    from qgis.gui import QgsMapCanvas

    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
    translation_patch = patch(
        "gaussian_educativo.i18n.language", return_value="es")
    translation_patch.start()
    warnings = []
    warning_patch = patch(
        "gaussian_educativo.dock.QMessageBox.warning",
        side_effect=lambda parent, title, message: warnings.append(str(message)))
    warning_patch.start()
    report = {"status": "failed", "scenarios": []}
    plugin = None
    try:
        canvas = QgsMapCanvas()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas.setDestinationCrs(wgs84)
        canvas.setExtent(QgsRectangle(-70.3, -20.9, -70.0, -20.7))
        window = QMainWindow()
        from gaussian_educativo.plugin import GaussianEducationalPlugin
        plugin = GaussianEducationalPlugin(FakeInterface(canvas, window))
        plugin.initGui()
        dock = plugin.dock
        dock.set_source(QgsPointXY(-70.193195, -20.805320), wgs84)

        cases = []
        for repeat in range(3):
            cases.append({
                "name": "three_sources_repeat_{}".format(repeat + 1),
                "offsets": [(0.0, 0.0), (0.010, 0.0), (0.040, 0.0)],
                "stability": 3, "wind_mode": 0, "wind_speed": 5.0,
                "resolution": 50.0, "height_mode": 0,
            })
        cases.extend([
            {
                "name": "six_sources_stability_f",
                "offsets": [(column * .012, row * .008)
                            for row in range(2) for column in range(3)],
                "stability": 5, "wind_mode": 0, "wind_speed": 2.0,
                "resolution": 100.0, "height_mode": 0,
            },
            {
                "name": "four_sources_briggs_e",
                "offsets": [(0.0, 0.0), (.012, .004),
                            (.024, -.004), (.036, .006)],
                "stability": 4, "wind_mode": 0, "wind_speed": 3.0,
                "resolution": 100.0, "height_mode": 2,
            },
            {
                "name": "five_sources_prevailing",
                "offsets": [(index * .009, (index % 2) * .005)
                            for index in range(5)],
                "stability": 3, "wind_mode": 1, "wind_speed": 5.0,
                "resolution": 200.0, "height_mode": 0,
            },
            {
                "name": "twenty_sources_constant",
                "offsets": [(column * .006, row * .004)
                            for row in range(4) for column in range(5)],
                "stability": 2, "wind_mode": 0, "wind_speed": 4.0,
                "resolution": 100.0, "height_mode": 0,
            },
        ])

        with tempfile.TemporaryDirectory(
                prefix="gaussian-multisource-stress-") as temp:
            dock.output_dir_edit.setText(temp)
            for case in cases:
                dock.stability_combo.setCurrentIndex(case["stability"])
                dock.wind_mode_combo.setCurrentIndex(case["wind_mode"])
                dock.wind_speed_spin.setValue(case["wind_speed"])
                dock.wind_from_spin.setValue(0.0)
                dock.height_mode_combo.setCurrentIndex(case["height_mode"])
                dock.width_spin.setValue(10000.0)
                dock.domain_height_spin.setValue(10000.0)
                dock.resolution_spin.setValue(case["resolution"])
                dock.domain_policy_combo.setCurrentIndex(1)
                base = dock._current_source_row("Fuente 1")
                rows = []
                for index, (delta_lon, delta_lat) in enumerate(
                        case["offsets"], start=1):
                    row = dict(
                        base, name="Fuente {}".format(index),
                        longitude=-70.193195 + delta_lon,
                        latitude=-20.805320 + delta_lat,
                        emission_kg_s=.005 + index * .001,
                        height_m=35.0 + index * 3.0)
                    if case["height_mode"] == 2:
                        row.update({
                            "diameter_m": 1.2 + index * .15,
                            "exit_velocity_m_s": 7.0 + index,
                            "temperature_c": 105.0 + index * 8.0,
                        })
                    rows.append(row)
                dock.sources = rows
                dock._invalidate_source_layer()
                dock._update_source_count()
                dock.scenario_edit.setText(case["name"])
                signal_result = []
                dock.start_execution()
                task = dock.active_task
                if task is None:
                    report["scenarios"].append({
                        "name": case["name"], "status": "not_started",
                        "panel": dock.status_label.text()})
                    continue
                loop = QEventLoop()
                task.executed.connect(
                    lambda successful, results, target=signal_result:
                        (target.append(bool(successful)), loop.quit()))
                QTimer.singleShot(120000, loop.quit)
                loop.exec()
                app.processEvents()
                target = Path(temp) / case["name"]
                scenario_path = target / "escenario.json"
                scenario = (json.loads(scenario_path.read_text())
                            if scenario_path.is_file() else {})
                outputs = {name: (target / name).is_file() for name in
                           ("concentracion.tif", "isolineas.gpkg",
                            "fuente.gpkg")}
                result = scenario.get("execution", {}).get("results", {})
                report["scenarios"].append({
                    "name": case["name"],
                    "sources": len(rows),
                    "signal_success": signal_result[-1]
                        if signal_result else False,
                    "task_released": dock.active_task is None,
                    "outputs": outputs,
                    "panel": dock.status_label.text(),
                    "domain_status": result.get("DOMAIN_STATUS"),
                    "domain_iterations": result.get("DOMAIN_ITERATIONS"),
                    "actual_width_m": result.get("ACTUAL_WIDTH"),
                    "actual_height_m": result.get("ACTUAL_HEIGHT"),
                    "maximum": result.get("MAXIMUM"),
                })
                QgsProject.instance().clear()

        passed = all(
            item.get("signal_success") and item.get("task_released") and
            all(item.get("outputs", {}).values()) and
            item.get("maximum", 0) > 0 and
            item.get("domain_iterations", 0) >= 1
            for item in report["scenarios"])
        report["warnings"] = warnings
        report["status"] = "passed" if passed and not warnings else "failed"
    finally:
        if plugin is not None:
            QgsProject.instance().clear()
            plugin.unload()
        warning_patch.stop()
        translation_patch.stop()
        app.exitQgis()

    output = ROOT / "validation/qgis_multisource_stress_0167.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
