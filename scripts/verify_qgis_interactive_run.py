"""QGIS --code helper: verify the installed dock and leave results visible."""
from pathlib import Path
import json
import traceback

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsProject
import qgis.utils


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "validation/qgis_installed_interactive.json"


def record_error():
    REPORT.write_text(json.dumps({"status": "failed", "error": traceback.format_exc()},
                                 indent=2, ensure_ascii=False) + "\n")


def activate():
    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:32719"))
        if "processing" not in qgis.utils.plugins:
            qgis.utils.loadPlugin("processing")
            qgis.utils.startPlugin("processing")
        name = "gaussian_educativo"
        if name not in qgis.utils.plugins:
            if not qgis.utils.loadPlugin(name) or not qgis.utils.startPlugin(name):
                raise RuntimeError("No se pudo iniciar el complemento instalado")
        plugin = qgis.utils.plugins[name]
        plugin.show_dock()
        dock = plugin.dock
        dock.set_source(QgsPointXY(-70.193195, -20.805320),
                        QgsCoordinateReferenceSystem("EPSG:4326"))
        dock.output_dir_edit.setText(str(ROOT / "outputs/qgis_interactive"))
        dock.scenario_edit.setText("Patache perfil habitual")
        dock.start_execution()
        if dock.active_task is None:
            raise RuntimeError("El panel no creó la tarea")

        def finished(successful, results):
            def save_evidence():
                try:
                    project_path = ROOT / "outputs/qgis_interactive/proyecto_patache_070.qgz"
                    project = QgsProject.instance()
                    project.setTitle("Patache · Panel QGIS 0.7")
                    project.write(str(project_path))
                    image_path = ROOT / "validation/qgis_installed_interactive.png"
                    qgis.utils.iface.mainWindow().grab().save(str(image_path), "PNG")
                    REPORT.write_text(json.dumps({
                        "status": "passed" if successful and
                            dock.status_label.text().startswith("Completado") else "failed",
                        "plugin_path": qgis.utils.pluginDirectory(name),
                        "panel_status": dock.status_label.text(),
                        "results": results,
                        "project": str(project_path),
                        "screenshot": str(image_path),
                    }, indent=2, ensure_ascii=False) + "\n")
                except Exception:
                    record_error()
            QTimer.singleShot(1500, save_evidence)

        dock.active_task.executed.connect(finished)
    except Exception:
        record_error()


QTimer.singleShot(1500, activate)
