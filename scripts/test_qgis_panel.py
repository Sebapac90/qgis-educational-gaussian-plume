"""Headless smoke test for the interactive dock and plugin lifecycle."""
from pathlib import Path
import json
import os
import sys
import tempfile
import shutil
from unittest.mock import patch

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PARENT = Path(os.environ.get("GAUSSIAN_QGIS_PLUGIN_PARENT",
                                    str(ROOT / "qgis_plugin")))
sys.path.insert(0, str(PLUGIN_PARENT))


class FakeInterface:
    def __init__(self, canvas, window):
        self._canvas = canvas
        self._window = window
        self.actions = []
        self.docks = []

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._window

    def addPluginToMenu(self, menu, action):
        self.actions.append((menu, action))

    def removePluginMenu(self, menu, action):
        self.actions.remove((menu, action))

    def addToolBarIcon(self, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addDockWidget(self, area, dock):
        self._window.addDockWidget(area, dock)
        self.docks.append(dock)

    def removeDockWidget(self, dock):
        self._window.removeDockWidget(dock)
        self.docks.remove(dock)


def main():
    contents = configure_macos_qgis_bundle()
    from qgis.PyQt.QtWidgets import QDialog, QMainWindow
    from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
                           QgsPointXY, QgsRectangle)
    from qgis.gui import QgsMapCanvas

    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
    translation_patch = patch("gaussian_educativo.i18n.language", return_value="es")
    translation_patch.start()
    try:
        canvas = QgsMapCanvas()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas.setDestinationCrs(wgs84)
        canvas.setExtent(QgsRectangle(-70.3, -20.9, -70.1, -20.7))
        window = QMainWindow()
        interface = FakeInterface(canvas, window)

        from gaussian_educativo.plugin import GaussianEducationalPlugin
        from gaussian_educativo.dock import WindCsvImportDialog
        plugin = GaussianEducationalPlugin(interface)
        plugin.initGui()
        dock = plugin.dock
        initially_unprepared = (
            dock.source_point is None and dock.wgs84_point is None and
            not dock.original_edit.text() and not dock.wgs84_edit.text() and
            not dock.calculation_edit.text())
        dock.set_source(QgsPointXY(-70.193195, -20.805320), wgs84)
        constant = dock.algorithm_parameters()
        dock.wind_mode_combo.setCurrentIndex(1)
        prevailing = dock.algorithm_parameters()
        dock.wind_mode_combo.setCurrentIndex(2)
        fluctuating = dock.algorithm_parameters()
        fluctuating_ignores_direction = not dock.wind_from_spin.isEnabled()
        dock.wind_mode_combo.setCurrentIndex(3)
        dock.csv_edit.setText(str(ROOT / "examples/synthetic_ne_sw_wind.csv"))
        table = dock.algorithm_parameters()
        dock.clear_csv()
        dock.emission_spin.setValue(12.5)
        dock.emission_unit_combo.setCurrentIndex(2)
        dock.wind_speed_spin.setValue(7.2)
        dock.wind_from_spin.setValue(225.0)
        dock.height_spin.setValue(80.0)
        dock.stability_combo.setCurrentIndex(5)
        dock.width_spin.setValue(20000.0)
        dock.domain_height_spin.setValue(30000.0)
        dock.resolution_spin.setValue(100.0)
        dock.domain_policy_combo.setCurrentIndex(1)
        dock.concentration_unit_combo.setCurrentIndex(2)
        dock.contour_minimum_spin.setValue(0.5)
        briggs_hidden_outside_mode = dock.briggs_button.isHidden()
        dock.height_mode_combo.setCurrentIndex(2)
        dock.stack_diameter_spin.setValue(2.5)
        dock.exit_velocity_spin.setValue(11.0)
        dock.stack_temperature_spin.setValue(130.0)
        dock.ambient_temperature_spin.setValue(25.0)
        dock.ambient_gradient_spin.setValue(2.5)
        dock.stack_tip_downwash_combo.setCurrentIndex(1)
        briggs_visible_in_mode = not dock.briggs_button.isHidden()
        briggs_dialog_parameters = dock.algorithm_parameters()
        briggs_dialog_configured = (
            dock.briggs_dialog.parent() is dock and
            dock.briggs_dialog.windowTitle() == 'Configurar elevación Briggs' and
            briggs_dialog_parameters['HEIGHT_MODE'] == 2 and
            briggs_dialog_parameters['STACK_DIAMETER'] == 2.5 and
            briggs_dialog_parameters['EXIT_VELOCITY'] == 11.0 and
            briggs_dialog_parameters['STACK_TEMPERATURE_C'] == 130.0 and
            briggs_dialog_parameters['AMBIENT_TEMPERATURE_C'] == 25.0 and
            briggs_dialog_parameters['AMBIENT_GRADIENT_C_KM'] == 2.5 and
            briggs_dialog_parameters['STACK_TIP_DOWNWASH'] == 1)
        before_briggs_cancel = dock.algorithm_parameters()

        def reject_changed_briggs_dialog():
            dock.stack_diameter_spin.setValue(4.0)
            dock.stack_tip_downwash_combo.setCurrentIndex(0)
            return QDialog.Rejected

        with patch.object(dock.briggs_dialog, 'exec',
                          side_effect=reject_changed_briggs_dialog):
            dock.configure_briggs()
        briggs_cancel_preserves_values = (
            dock.algorithm_parameters() == before_briggs_cancel)
        customized = dock.algorithm_parameters()
        with tempfile.TemporaryDirectory(prefix="gaussian-panel-") as temporary:
            import_source = Path(temporary) / "viento_usuario.csv"
            import_source.write_text(
                "fecha;rumbo;rapidez\n"
                "01/01/2025 00:00;NE;10\n"
                "01/01/2025 01:00;.;8\n"
                "01/01/2025 02:00;S;0\n",
                encoding="utf-8")
            import_dialog = WindCsvImportDialog(import_source, dock)
            import_dialog.date_format_combo.setCurrentIndex(
                import_dialog.date_format_combo.findData("%d/%m/%Y %H:%M"))
            import_dialog.direction_format_combo.setCurrentIndex(1)
            import_dialog.speed_unit_combo.setCurrentIndex(2)
            import_dialog._prepare()
            importer_passed = (
                import_dialog.result() == import_dialog.Accepted and
                import_dialog.output_path.is_file() and
                import_dialog.summary.total_rows == 3 and
                import_dialog.summary.rows == 1 and
                import_dialog.summary.excluded_variable_rows == 1 and
                import_dialog.summary.excluded_calm_rows == 1)
            import_dialog.close()
            dock.output_dir_edit.setText(temporary)
            dock.scenario_edit.setText("Patache docente")
            direct_parameters, direct_directory, direct_name = \
                dock.execution_parameters()
            direct_paths = {key: direct_parameters[key] for key in
                            ("OUTPUT", "ISOLINES", "SOURCE_OUTPUT")}
            scenario_file = Path(temporary) / "guardado.json"
            dock.save_scenario(scenario_file)
            dock.emission_spin.setValue(0.0)
            dock.load_scenario(scenario_file)
            roundtrip = dock.algorithm_parameters() == customized
            dock.csv_edit.setText(str(ROOT / "examples/synthetic_ne_sw_wind.csv"))
            dock.wind_mode_combo.setCurrentIndex(3)
            table_file = Path(temporary) / "tabla.json"
            dock.save_scenario(table_file)
            dock.csv_edit.clear()
            dock.load_scenario(table_file)
            copied_csv = Path(dock.csv_edit.text())
            csv_recovered = copied_csv.is_file() and copied_csv.parent == Path(temporary)
            moved = Path(temporary) / "trasladado"
            moved.mkdir()
            shutil.copy2(table_file, moved / table_file.name)
            shutil.copy2(copied_csv, moved / copied_csv.name)
            with patch("gaussian_educativo.dock.QFileDialog.getOpenFileName",
                       return_value=(str(moved / table_file.name), "JSON")):
                dock.load_scenario_button.click()
            portable_csv = Path(dock.csv_edit.text()).parent == moved
            saved_by_button = moved / "boton.json"
            with patch("gaussian_educativo.dock.QFileDialog.getSaveFileName",
                       return_value=(str(saved_by_button), "JSON")):
                dock.save_scenario_button.click()
            button_save = saved_by_button.is_file()
            before_cancel = dock.algorithm_parameters()
            with patch("gaussian_educativo.dock.QFileDialog.getOpenFileName",
                       return_value=("", "")):
                dock.load_scenario_button.click()
            canceled_dialog_unchanged = dock.algorithm_parameters() == before_cancel
            invalid_file = moved / "invalido.json"
            invalid = json.loads(saved_by_button.read_text())
            invalid["parameters"]["WIDTH"] = 100001
            invalid_file.write_text(json.dumps(invalid))
            try:
                dock.load_scenario(invalid_file)
                invalid_unchanged = False
            except ValueError:
                invalid_unchanged = dock.algorithm_parameters() == before_cancel
            copied_csv.write_text("alterado\n")
            try:
                dock.load_scenario(table_file)
                tamper_rejected = False
            except ValueError:
                tamper_rejected = True

        report = {
            "status": "passed",
            "original": dock.original_edit.text(),
            "wgs84": dock.wgs84_edit.text(),
            "calculation": dock.calculation_edit.text(),
            "constant_parameters": constant,
            "table_parameters": table,
            "prevailing_parameters": prevailing,
            "fluctuating_parameters": fluctuating,
            "customized_parameters": customized,
            "algorithm_registered":
                QgsApplication.processingRegistry().algorithmById(
                    dock.ALGORITHM_ID) is not None,
            "action_registered": len(interface.actions) == 1,
            "dock_registered": len(interface.docks) == 1,
            "initially_unprepared": initially_unprepared,
            "direct_scenario": direct_name,
            "direct_directory": direct_directory.name,
            "direct_paths": direct_paths,
            "scenario_roundtrip": roundtrip,
            "csv_copy_recovered": csv_recovered,
            "changed_csv_rejected": tamper_rejected,
            "portable_csv_recovered": portable_csv,
            "save_button_handler": button_save,
            "canceled_file_dialog_unchanged": canceled_dialog_unchanged,
            "invalid_scenario_preserves_inputs": invalid_unchanged,
            "csv_import_dialog": importer_passed,
            "briggs_hidden_outside_mode": briggs_hidden_outside_mode,
            "briggs_visible_in_mode": briggs_visible_in_mode,
            "briggs_dialog_configured": briggs_dialog_configured,
            "briggs_cancel_preserves_values": briggs_cancel_preserves_values,
        }
        checks = [
            "EPSG:4326" in report["original"],
            "lon -70.19319500" in report["wgs84"],
            "EPSG:32719" in report["calculation"],
            "E 375825.819" in report["calculation"],
            "N 7698938.582" in report["calculation"],
            constant["WIND_MODE"] == 0,
            prevailing["WIND_MODE"] == 1,
            prevailing["WIND_FROM"] == constant["WIND_FROM"],
            fluctuating["WIND_MODE"] == 2,
            fluctuating_ignores_direction,
            constant["SOURCE"].endswith("[EPSG:4326]"),
            table["WIND_MODE"] == 3,
            table["DOMAIN_POLICY"] == 0,
            table["WIND_FILE"].endswith("synthetic_ne_sw_wind.csv"),
            customized["EMISSION"] == 12.5,
            customized["EMISSION_UNIT"] == 2,
            customized["WIND_SPEED"] == 7.2,
            customized["WIND_FROM"] == 225.0,
            customized["EFFECTIVE_HEIGHT"] == 80.0,
            customized["STABILITY"] == 5,
            customized["WIND_REFERENCE_HEIGHT"] == 10.0,
            customized["WIND_EXPOSURE"] == 0,
            customized["WIDTH"] == 20000.0,
            customized["HEIGHT"] == 30000.0,
            customized["RESOLUTION"] == 100.0,
            customized["DOMAIN_POLICY"] == 1,
            customized["CONCENTRATION_UNIT"] == 2,
            customized["CONTOUR_MINIMUM"] == 0.5,
            report["algorithm_registered"],
            report["action_registered"],
            report["dock_registered"],
            report["initially_unprepared"],
            roundtrip, csv_recovered, tamper_rejected,
            portable_csv, button_save, canceled_dialog_unchanged, invalid_unchanged,
            importer_passed,
            briggs_hidden_outside_mode, briggs_visible_in_mode,
            briggs_dialog_configured, briggs_cancel_preserves_values,
            report["direct_scenario"] == "Patache docente",
            report["direct_directory"] == "Patache_docente",
            direct_paths["OUTPUT"].endswith(
                "Patache_docente/concentracion.tif"),
            direct_paths["ISOLINES"].endswith(
                "Patache_docente/isolineas.gpkg"),
            direct_paths["SOURCE_OUTPUT"].endswith(
                "Patache_docente/fuente.gpkg"),
        ]
        if not all(checks):
            report["status"] = "failed"
        plugin.unload()
        report["clean_unload"] = (
            not interface.actions and not interface.docks and
            QgsApplication.processingRegistry().algorithmById(
                dock.ALGORITHM_ID) is None)
        if not report["clean_unload"]:
            report["status"] = "failed"
        dock = None
        plugin = None
        canvas = None
        window = None
    finally:
        translation_patch.stop()
        app.exitQgis()

    output = ROOT / "validation/qgis_panel.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
