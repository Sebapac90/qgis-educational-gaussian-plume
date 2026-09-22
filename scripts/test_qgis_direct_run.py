"""Exercise the dock's asynchronous base-case run with the QGIS runtime."""
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
        Path(tempfile.gettempdir()) / "gaussian-qgis-direct-profile")
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtWidgets import QMainWindow
    from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
                           QgsPointXY, QgsProject, QgsRectangle)
    from qgis.gui import QgsMapCanvas

    app = QgsApplication([], False)
    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    configure_application(app, contents)
    app.initQgis()
    translation_patch = patch("gaussian_educativo.i18n.language", return_value="es")
    translation_patch.start()
    def fail_warning(parent, title, message):
        raise RuntimeError(message)
    warning_patch = patch("gaussian_educativo.dock.QMessageBox.warning",
                          side_effect=fail_warning)
    warning_patch.start()
    report = {"status": "failed"}
    try:
        canvas = QgsMapCanvas()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas.setDestinationCrs(wgs84)
        canvas.setExtent(QgsRectangle(-70.3, -20.9, -70.1, -20.7))
        window = QMainWindow()
        from gaussian_educativo.plugin import GaussianEducationalPlugin
        plugin = GaussianEducationalPlugin(FakeInterface(canvas, window))
        plugin.initGui()
        dock = plugin.dock
        dock.set_source(QgsPointXY(-70.193195, -20.805320), wgs84)
        with tempfile.TemporaryDirectory(prefix="gaussian-direct-") as temp:
            dock.output_dir_edit.setText(temp)
            dock.scenario_edit.setText("Patache directo")
            dock.start_execution()
            task = dock.active_task
            if task is None:
                raise RuntimeError("El panel no creó la tarea")
            loop = QEventLoop()
            task.executed.connect(lambda successful, results: loop.quit())
            QTimer.singleShot(30000, loop.quit)
            loop.exec()
            app.processEvents()
            target = Path(temp) / "Patache_directo"
            files = {name: (target / name).is_file() for name in
                     ("concentracion.tif", "isolineas.gpkg", "fuente.gpkg")}
            groups = [child.name() for child in
                      QgsProject.instance().layerTreeRoot().children()]
            report = {
                "files": files,
                "layers": sorted(layer.name() for layer in
                                 QgsProject.instance().mapLayers().values()),
                "group_created": any(
                    name.startswith("Pluma · Patache directo")
                    for name in groups),
                "panel_status": dock.status_label.text(),
                "progress": dock.progress_bar.value(),
                "canvas_extent": [canvas.extent().xMinimum(),
                                  canvas.extent().yMinimum(),
                                  canvas.extent().xMaximum(),
                                  canvas.extent().yMaximum()],
            }
            report["canvas_zoom_matches_crs"] = (
                -71 < canvas.extent().xMinimum() < -70 and
                -21 < canvas.extent().yMinimum() < -20 and
                -71 < canvas.extent().xMaximum() < -70 and
                -21 < canvas.extent().yMaximum() < -20)
            dock.csv_edit.setText(str(
                ROOT / "examples/synthetic_ne_sw_wind.csv"))
            dock.wind_mode_combo.setCurrentIndex(3)
            dock.scenario_edit.setText("Cancelar tabla")
            cancel_parameters_before = dock.algorithm_parameters()
            dock.start_execution()
            cancel_task = dock.active_task
            if cancel_task is None:
                raise RuntimeError("El panel no creó la tarea cancelable")
            cancel_loop = QEventLoop()
            cancel_task.executed.connect(
                lambda successful, results: cancel_loop.quit())
            QTimer.singleShot(10, dock.cancel_execution)
            QTimer.singleShot(30000, cancel_loop.quit)
            cancel_loop.exec()
            app.processEvents()
            cancel_files = list((Path(temp) / "Cancelar_tabla").glob("*"))
            cancel_record = json.loads(
                (Path(temp) / "Cancelar_tabla/escenario.json").read_text())
            report["cancellation"] = {
                "task_released": dock.active_task is None,
                "status": dock.status_label.text(),
                "result_files": [path.name for path in cancel_files],
                "record_status": cancel_record["execution"]["status"],
                "parameters_before": cancel_parameters_before,
                "parameters_saved": cancel_record["parameters"],
            }
            report["status"] = "passed" if (
                all(files.values()) and report["group_created"] and
                report["canvas_zoom_matches_crs"] and
                report["cancellation"]["task_released"] and
                "cancelado" in report["cancellation"]["status"].lower() and
                cancel_record["execution"]["status"] == "canceled" and
                cancel_parameters_before["WIND_MODE"] == 3 and
                cancel_record["parameters"]["WIND_MODE"] == 3 and
                (Path(temp) / "Cancelar_tabla/escenario_viento.csv").is_file()) else "failed"
        QgsProject.instance().clear()
        plugin.unload()
    finally:
        warning_patch.stop()
        translation_patch.stop()
        app.exitQgis()
    output = ROOT / "validation/qgis_direct_run.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
