"""QGIS --code: reopen a saved scenario and compare two actual dock runs."""
from pathlib import Path
import configparser
import json
import traceback

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsProject
import qgis.utils


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "validation/qgis_scenario_roundtrip.json"
NAME = "gaussian_educativo"


def error():
    REPORT.write_text(json.dumps({"status": "failed", "error": traceback.format_exc()},
                                 indent=2, ensure_ascii=False) + "\n")


def start_plugin():
    if NAME not in qgis.utils.plugins:
        if not qgis.utils.loadPlugin(NAME) or not qgis.utils.startPlugin(NAME):
            raise RuntimeError("No se pudo cargar Gaussian")
    plugin = qgis.utils.plugins[NAME]
    plugin.show_dock()
    return plugin.dock


def activate():
    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:32719"))
        qgis.utils.loadPlugin("processing")
        qgis.utils.startPlugin("processing")
        dock = start_plugin()
        dock.set_source(QgsPointXY(375825.81901894213, 7698938.582415143),
                        QgsCoordinateReferenceSystem("EPSG:32719"))
        dock.scenario_edit.setText("Patache escenario recuperable")
        dock.output_dir_edit.setText(str(ROOT / "outputs/qgis_scenarios"))
        initial_parameters = dock.algorithm_parameters()
        dock.start_execution()
        first_record = dock.running_scenario_file
        if dock.active_task is None:
            raise RuntimeError("No se creó la primera tarea")

        def first_finished(successful, first_results):
            if not successful:
                REPORT.write_text(json.dumps({"status": "failed", "stage": "first_run"}))
                return

            def reopen():
                try:
                    qgis.utils.unloadPlugin(NAME)
                    project.clear()
                    project.setCrs(QgsCoordinateReferenceSystem("EPSG:32719"))
                    restored = start_plugin()
                    restored.load_scenario(first_record)
                    parameters_match = restored.algorithm_parameters() == initial_parameters
                    restored.start_execution()
                    if restored.active_task is None:
                        raise RuntimeError("No se creó la segunda tarea")

                    def second_finished(second_success, second_results):
                        def save():
                            try:
                                project_path = ROOT / "outputs/qgis_scenarios/proyecto_patache_080.qgz"
                                project.setTitle("Patache · Escenario recuperado · Gaussian 0.8")
                                project_saved = project.write(str(project_path))
                                screenshot = ROOT / "validation/qgis_scenario_roundtrip.png"
                                screenshot_saved = qgis.utils.iface.mainWindow().grab().save(str(screenshot), "PNG")
                                compared = ("MAXIMUM", "BORDER_MAXIMUM", "OUTPUT_CRS",
                                            "ACTUAL_WIDTH", "ACTUAL_HEIGHT", "DOMAIN_STATUS")
                                results_match = all(first_results[key] == second_results[key]
                                                    for key in compared)
                                metadata = configparser.ConfigParser()
                                metadata.read(str(Path(qgis.utils.pluginDirectory(NAME)) / "metadata.txt"))
                                report = {
                                    "status": "passed" if second_success and parameters_match and
                                        results_match and project_saved and screenshot_saved else "failed",
                                    "plugin_version": metadata["general"]["version"],
                                    "parameters_match": parameters_match,
                                    "results_match": results_match,
                                    "original_crs": restored.source_crs.authid(),
                                    "first_scenario": str(first_record),
                                    "second_scenario": str(restored.running_scenario_file),
                                    "maximum": second_results.get("MAXIMUM"),
                                    "border_maximum": second_results.get("BORDER_MAXIMUM"),
                                    "project": str(project_path),
                                    "screenshot": str(screenshot),
                                }
                                REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
                            except Exception:
                                error()
                        QTimer.singleShot(1500, save)
                    restored.active_task.executed.connect(second_finished)
                except Exception:
                    error()
            QTimer.singleShot(500, reopen)
        dock.active_task.executed.connect(first_finished)
    except Exception:
        error()


QTimer.singleShot(1500, activate)
