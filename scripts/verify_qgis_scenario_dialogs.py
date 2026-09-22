"""QGIS --code: real Qt file dialogs and a Spanish/English scenario rerun.

Run only in a disposable profile. No file-selector mocks are used. Qt dialogs
are selected explicitly, so this does not certify macOS native file dialogs.
"""
from pathlib import Path
from datetime import datetime
import configparser
import json
import traceback
import platform
import os

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QLineEdit
from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsPointXY,
                       QgsProject, QgsSettings)
import qgis.utils

ROOT = Path(__file__).resolve().parents[1]
VERSION = os.environ.get("GAUSSIAN_PLUGIN_TEST_VERSION", "0.14.0")
VERSION_TAG = VERSION.replace(".", "")
REPORT = ROOT / ("validation/qgis_scenario_dialogs_" + VERSION_TAG + ".json")
TARGET = ROOT / "outputs/qgis_dialogs" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
NAME = "gaussian_educativo"
checks = {}


def finish(error=None):
    report = {"status": "failed" if error or not all(checks.values()) else "passed",
              "plugin_version": VERSION, "checks": checks,
              "qgis": Qgis.QGIS_VERSION, "python": platform.python_version(),
              "dialog_backend": "real Qt widgets, not native macOS dialogs",
              "output_directory": str(TARGET)}
    if error:
        report["error"] = error
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    QgsApplication.instance().quit()


def file_dialog(button, filename=None, cancel=False):
    completed = []
    attempts = []
    errors = []

    def choose():
        try:
            dialog = QApplication.activeModalWidget()
            if not isinstance(dialog, QFileDialog):
                attempts.append(1)
                if len(attempts) < 50:
                    QTimer.singleShot(100, choose)
                    return
                raise RuntimeError("No apareció el selector Qt")
            if not cancel:
                dialog.setDirectory(str(filename.parent))
                dialog.selectFile(str(filename))
                name_edit = dialog.findChild(QLineEdit, "fileNameEdit")
                if name_edit is None:
                    raise RuntimeError("No se encontró el campo de nombre de archivo")
                name_edit.setText(filename.name)
                screenshot = TARGET / (filename.stem + "_dialog.png")
                checks["dialog_screenshot_" + filename.stem] = dialog.grab().save(str(screenshot), "PNG")
            box = dialog.findChild(QDialogButtonBox)
            role = QDialogButtonBox.RejectRole if cancel else QDialogButtonBox.AcceptRole
            selected_button = next(b for b in box.buttons() if box.buttonRole(b) == role)
            if not selected_button.isEnabled():
                raise RuntimeError("El botón del selector de archivo no está habilitado")
            selected_button.click()
            completed.append(True)
        except Exception:
            errors.append(traceback.format_exc())
            completed.append(False)
            if QApplication.activeModalWidget() is not None:
                QApplication.activeModalWidget().reject()

    QTimer.singleShot(200, choose)
    button.click()  # Enters the real dialog's nested Qt event loop.
    if completed != [True]:
        raise RuntimeError("No se pudo completar el diálogo de archivo: " + "\n".join(errors))


def set_language(locale):
    settings = QgsSettings()
    settings.setValue("locale/overrideFlag", True)
    settings.setValue("locale/userLocale", locale)


def activate():
    try:
        TARGET.mkdir(parents=True, exist_ok=False)
        checks["normal_startup"] = NAME in qgis.utils.plugins
        plugin = qgis.utils.plugins[NAME]
        metadata = configparser.ConfigParser()
        metadata.read(str(Path(qgis.utils.pluginDirectory(NAME)) / "metadata.txt"))
        checks["installed_version"] = metadata["general"]["version"] == VERSION
        # Only this disposable profile is changed.
        qgis.utils.unloadPlugin(NAME)
        set_language("es_CL")
        qgis.utils.loadPlugin(NAME)
        qgis.utils.startPlugin(NAME)
        plugin = qgis.utils.plugins[NAME]
        plugin.show_dock()
        dock = plugin.dock
        project = QgsProject.instance()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:32719"))
        dock.set_source(QgsPointXY(375825.81901894213, 7698938.582415143),
                        QgsCoordinateReferenceSystem("EPSG:32719"))
        dock.output_dir_edit.setText(str(TARGET))
        dock.scenario_edit.setText("Patache · prueba de diálogos")
        original = dock.algorithm_parameters()
        checks["spanish_controls"] = dock.run_button.text() == "Ejecutar y cargar capas"
        saved = TARGET / "escenario_guardado.json"
        file_dialog(dock.save_scenario_button, saved)
        checks["save_dialog_writes_json"] = saved.is_file()
        dock.emission_spin.setValue(15)
        canceled_inputs = dock.algorithm_parameters()
        file_dialog(dock.load_scenario_button, cancel=True)
        checks["cancel_open_preserves_inputs"] = dock.algorithm_parameters() == canceled_inputs
        file_dialog(dock.load_scenario_button, saved)
        checks["open_dialog_restores_inputs"] = dock.algorithm_parameters() == original
        dock.run_button.click()
        if dock.active_task is None:
            raise RuntimeError("No se creó la primera tarea")

        def first_done(successful, first_results):
            def reopen_english():
                try:
                    checks["first_run"] = successful
                    qgis.utils.unloadPlugin(NAME)
                    set_language("en_US")
                    qgis.utils.loadPlugin(NAME)
                    qgis.utils.startPlugin(NAME)
                    restored = qgis.utils.plugins[NAME].dock
                    qgis.utils.plugins[NAME].show_dock()
                    checks["english_controls"] = restored.run_button.text() == "Run and load layers"
                    file_dialog(restored.load_scenario_button, saved)
                    checks["cross_language_inputs_match"] = restored.algorithm_parameters() == original
                    checks["original_utm_preserved"] = restored.source_crs.authid() == "EPSG:32719"
                    restored.run_button.click()
                    if restored.active_task is None:
                        raise RuntimeError("No se creó la segunda tarea")

                    def second_done(second_success, second_results):
                        def save_project():
                            try:
                                checks["second_run"] = second_success
                                keys = ("MAXIMUM", "BORDER_MAXIMUM", "OUTPUT_CRS",
                                        "ACTUAL_WIDTH", "ACTUAL_HEIGHT", "DOMAIN_STATUS")
                                checks["results_identical"] = all(first_results[k] == second_results[k]
                                                                 for k in keys)
                                checks["fresh_output_directory"] = first_results["OUTPUT"] != second_results["OUTPUT"]
                                from osgeo import gdal
                                import numpy as np
                                a = gdal.Open(first_results["OUTPUT"])
                                b = gdal.Open(second_results["OUTPUT"])
                                checks["all_raster_pixels_identical"] = bool(np.array_equal(a.ReadAsArray(), b.ReadAsArray()))
                                a = b = None
                                checks["project_saved"] = project.write(str(TARGET / ("proyecto_patache_" + VERSION_TAG + ".qgz")))
                                checks["map_screenshot"] = qgis.utils.iface.mainWindow().grab().save(
                                    str(TARGET / "qgis_english.png"), "PNG")
                                finish()
                            except Exception:
                                finish(traceback.format_exc())
                        QTimer.singleShot(1500, save_project)
                    restored.active_task.executed.connect(second_done)
                except Exception:
                    finish(traceback.format_exc())
            QTimer.singleShot(500, reopen_english)
        dock.active_task.executed.connect(first_done)
    except Exception:
        finish(traceback.format_exc())


QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
QTimer.singleShot(5000, activate)
QTimer.singleShot(60000, lambda: finish("timeout"))
