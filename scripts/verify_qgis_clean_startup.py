"""QGIS --code acceptance check in a disposable profile, with normal loading."""
from pathlib import Path
import json
import traceback

from qgis.PyQt.QtCore import QPoint, Qt, QTimer
from qgis.PyQt.QtTest import QTest
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsProject,
                       QgsRectangle, QgsVectorLayer)
import qgis.utils

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "validation/qgis_clean_startup.json"


def finish(report):
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    QgsApplication.instance().quit()


def verify():
    try:
        # Do not load plugins here: normal QGIS startup must have loaded them.
        plugin = qgis.utils.plugins["gaussian_educativo"]
        registered = QgsApplication.processingRegistry().algorithmById(
            "gaussian_educativo:simular_pluma") is not None
        iface = qgis.utils.iface
        project = QgsProject.instance()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        # An existing map prevents QGIS choosing the first result's UTM CRS.
        anchor = QgsVectorLayer("Point?crs=EPSG:4326", "Mapa WGS84 de prueba", "memory")
        project.addMapLayer(anchor)
        canvas = iface.mapCanvas()
        canvas.setDestinationCrs(project.crs())
        canvas.setExtent(QgsRectangle(-70.24, -20.85, -70.15, -20.76))
        plugin.show_dock()
        dock = plugin.dock
        previous = canvas.mapTool()
        dock.capture_button.click()
        viewport = canvas.viewport()
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier,
                         QPoint(viewport.width() // 2, viewport.height() // 2))
        captured = dock.source_point is not None and canvas.mapTool() == previous
        if not captured:
            raise RuntimeError("La selección en el lienzo no preparó la fuente")
        dock.scenario_edit.setText("Prueba arranque normal 081")
        dock.output_dir_edit.setText(str(ROOT / "outputs/qgis_acceptance"))
        dock.run_button.click()
        if dock.active_task is None:
            raise RuntimeError("El botón Ejecutar no creó la tarea")

        def executed(successful, results):
            def save():
                try:
                    project.removeMapLayer(anchor.id())
                    path = ROOT / "outputs/qgis_acceptance/proyecto_validacion_081.qgz"
                    saved = project.write(str(path))
                    screenshot = ROOT / "validation/qgis_clean_startup.png"
                    captured_image = iface.mainWindow().grab().save(str(screenshot), "PNG")
                    extent = canvas.extent()
                    zoom_ok = -71 < extent.xMinimum() < -70 and -21 < extent.yMinimum() < -20
                    finish({"status": "passed" if successful and registered and captured
                            and saved and captured_image and zoom_ok else "failed",
                            "normal_startup": True, "plugin_registered": registered,
                            "qt_canvas_click": captured, "wgs84_zoom": zoom_ok,
                            "loaded_plugins": sorted(qgis.utils.plugins),
                            "results": results, "project": str(path),
                            "screenshot": str(screenshot)})
                except Exception:
                    finish({"status": "failed", "error": traceback.format_exc()})
            QTimer.singleShot(1500, save)
        dock.active_task.executed.connect(executed)
    except Exception:
        finish({"status": "failed", "error": traceback.format_exc()})


QTimer.singleShot(5000, verify)
QTimer.singleShot(45000, lambda: finish({"status": "failed", "error": "startup timeout"}))
