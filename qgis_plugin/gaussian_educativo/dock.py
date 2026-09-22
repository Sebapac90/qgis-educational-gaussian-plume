# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""QGIS dock that prepares and runs the validated Processing algorithm."""
from .i18n import tr
from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import tempfile

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsPointXY, QgsProcessingAlgRunnerTask,
    QgsProcessingContext, QgsProcessingFeedback, QgsProject, QgsRasterLayer,
    QgsVectorLayer)
from qgis.gui import QgsDockWidget, QgsMapToolEmitPoint

from .gaussian_spatial import locate_source_coordinates
from .gaussian_wind_import import normalize_wind_csv, read_wind_csv_preview
from .styles import style_isolines, style_raster, style_source


class WindCsvImportDialog(QDialog):
    """Map a simple three-column wind table to the canonical plugin CSV."""

    DATE_FORMATS = (
        ("ISO 8601 / automático", ""),
        ("AAAA-MM-DD HH:MM:SS", "%Y-%m-%d %H:%M:%S"),
        ("AAAA-MM-DD HH:MM", "%Y-%m-%d %H:%M"),
        ("DD-MM-AAAA HH:MM:SS", "%d-%m-%Y %H:%M:%S"),
        ("DD-MM-AAAA HH:MM", "%d-%m-%Y %H:%M"),
        ("DD/MM/AAAA HH:MM", "%d/%m/%Y %H:%M"),
    )

    def __init__(self, source_path, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path)
        self.output_path = None
        self.summary = None
        self.setWindowTitle(tr('Preparar tabla de viento'))
        self.resize(760, 520)
        headers, rows = read_wind_csv_preview(self.source_path)

        layout = QVBoxLayout(self)
        note = QLabel(tr(
            'Asigna las tres columnas. El archivo original no se modifica; '
            'se creará una copia normalizada para el cálculo.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index,
                              QTableWidgetItem(str(value)))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(table)

        form = QFormLayout()
        self.timestamp_combo = QComboBox()
        self.direction_combo = QComboBox()
        self.speed_combo = QComboBox()
        for combo in (self.timestamp_combo, self.direction_combo,
                      self.speed_combo):
            combo.addItems(headers)
        self._guess_column(self.timestamp_combo, headers,
                           ("time", "date", "fecha", "hora", "momento"))
        self._guess_column(self.direction_combo, headers,
                           ("direction", "direccion", "dirección", "dir", "dd", "rumbo"))
        self._guess_column(self.speed_combo, headers,
                           ("speed", "velocidad", "rapidez", "intensidad", "ff"))

        self.date_format_combo = QComboBox()
        for label, value in self.DATE_FORMATS:
            self.date_format_combo.addItem(tr(label), value)
        self.date_format_combo.setEditable(True)
        self.timezone_combo = QComboBox()
        self.timezone_combo.setEditable(True)
        self.timezone_combo.addItems(
            ["UTC", "America/Santiago", "America/New_York",
             "Europe/Madrid", "Australia/Sydney"])
        self.speed_unit_combo = QComboBox()
        self.speed_unit_combo.addItems(["m/s", "km/h", tr('nudos')])
        self.direction_format_combo = QComboBox()
        self.direction_format_combo.addItems(
            [tr('Grados 0–360'), tr('Rumbo cardinal')])
        self.direction_convention_combo = QComboBox()
        self.direction_convention_combo.addItems(
            [tr('DESDE (meteorológica)'), tr('HACIA')])
        self.calm_edit = QLineEdit("CALM, CALMA")
        self.variable_edit = QLineEdit("VRB, .")
        self.missing_edit = QLineEdit("-, NA, N/A")

        form.addRow(tr('Columna fecha/hora:'), self.timestamp_combo)
        form.addRow(tr('Formato de fecha:'), self.date_format_combo)
        form.addRow(tr('Zona horaria IANA:'), self.timezone_combo)
        form.addRow(tr('Columna dirección:'), self.direction_combo)
        form.addRow(tr('Representación:'), self.direction_format_combo)
        form.addRow(tr('Convención:'), self.direction_convention_combo)
        form.addRow(tr('Columna rapidez:'), self.speed_combo)
        form.addRow(tr('Unidad de rapidez:'), self.speed_unit_combo)
        form.addRow(tr('Códigos de calma:'), self.calm_edit)
        form.addRow(tr('Códigos de dirección variable:'), self.variable_edit)
        form.addRow(tr('Códigos ausentes:'), self.missing_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._prepare)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _guess_column(combo, headers, candidates):
        for index, header in enumerate(headers):
            lowered = header.casefold()
            if any(candidate in lowered for candidate in candidates):
                combo.setCurrentIndex(index)
                return

    def _prepare(self):
        selected = {self.timestamp_combo.currentText(),
                    self.direction_combo.currentText(),
                    self.speed_combo.currentText()}
        if len(selected) != 3:
            QMessageBox.warning(
                self, tr('Tabla de viento'),
                tr('Seleccione tres columnas diferentes.'))
            return
        unit = ("m/s", "km/h", "kn")[self.speed_unit_combo.currentIndex()]
        date_format = self.date_format_combo.currentData()
        if date_format is None:
            date_format = self.date_format_combo.currentText().strip()
        target_dir = Path(tempfile.gettempdir()) / "gaussian_educativo_imports"
        target_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            str(self.source_path.resolve()).encode("utf-8")).hexdigest()[:12]
        target = target_dir / (self.source_path.stem + "_" + digest + ".csv")
        try:
            self.summary = normalize_wind_csv(
                self.source_path, target,
                timestamp_column=self.timestamp_combo.currentText(),
                direction_column=self.direction_combo.currentText(),
                speed_column=self.speed_combo.currentText(),
                speed_unit=unit,
                timezone_name=self.timezone_combo.currentText().strip() or None,
                date_format=date_format or None,
                direction_format=("degrees", "cardinal")[
                    self.direction_format_combo.currentIndex()],
                direction_convention=("from", "to")[
                    self.direction_convention_combo.currentIndex()],
                calm_tokens=self.calm_edit.text(),
                variable_tokens=self.variable_edit.text(),
                missing_tokens=self.missing_edit.text())
        except Exception as error:
            QMessageBox.warning(self, tr('Tabla de viento'), str(error))
            return
        self.output_path = target
        self.accept()


class GaussianDock(QgsDockWidget):
    """Select a source, inspect coordinates and run the teaching case."""

    ALGORITHM_ID = "gaussian_educativo:simular_pluma"

    def __init__(self, iface, parent=None):
        super().__init__(tr('Pluma Gaussiana Educativa'), parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.previous_map_tool = None
        self.source_point = None
        self.source_crs = None
        self.wgs84_point = None
        self.active_task = None
        self.task_context = None
        self.task_feedback = None
        self.running_scenario = None
        self.running_unit_index = 3
        self.running_unit_label = "µg/m³"
        self.running_scenario_file = None
        self.wind_import_summary = None
        self.wind_original_path = None
        self.map_tool = QgsMapToolEmitPoint(self.canvas)
        self.map_tool.canvasClicked.connect(self._canvas_clicked)
        self.setObjectName("GaussianEducationalDock")
        self.setMinimumWidth(420)
        self._build_ui()
        self.status_label.setText(
            tr('Elige un punto en el mapa o usa el centro visible del lienzo.'))

    @staticmethod
    def _spin(value, minimum, maximum, decimals=3, suffix=""):
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        return widget

    @staticmethod
    def _combo(items, current=0):
        widget = QComboBox()
        widget.addItems(items)
        widget.setCurrentIndex(current)
        widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(6)
        return widget

    @staticmethod
    def _allow_narrow(widget):
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    @staticmethod
    def _group(title, form):
        group = QGroupBox(title)
        group.setLayout(form)
        return group

    def _build_ui(self):
        body = QWidget(self)
        layout = QVBoxLayout(body)
        introduction = QLabel(
            tr('Elige la fuente, revisa los parámetros y ejecuta el caso. El cálculo conserva el CRS original y usa UTM/UPS automáticamente.'))
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        buttons = QHBoxLayout()
        self.capture_button = QPushButton(tr('Elegir en el mapa'))
        self.center_button = QPushButton(tr('Usar centro'))
        self.capture_button.clicked.connect(self.start_capture)
        self.center_button.clicked.connect(self.use_canvas_center)
        buttons.addWidget(self.capture_button)
        buttons.addWidget(self.center_button)
        layout.addLayout(buttons)

        form = QFormLayout()
        self.original_edit = QLineEdit()
        self.wgs84_edit = QLineEdit()
        self.calculation_edit = QLineEdit()
        for widget in (self.original_edit, self.wgs84_edit,
                       self.calculation_edit):
            widget.setReadOnly(True)
            self._allow_narrow(widget)
        form.addRow(tr('Entrada:'), self.original_edit)
        form.addRow("WGS84:", self.wgs84_edit)
        form.addRow(tr('Cálculo:'), self.calculation_edit)
        layout.addWidget(self._group(tr('Fuente'), form))

        model_form = QFormLayout()
        emission_row = QHBoxLayout()
        self.emission_spin = self._spin(40.0, 0.0, 1e12, 6)
        self.emission_unit_combo = self._combo(
            ["kg/s", "g/s", "mg/s", "µg/s"], 1)
        emission_row.addWidget(self.emission_spin)
        emission_row.addWidget(self.emission_unit_combo)
        self.height_spin = self._spin(50.0, 0.0, 100000.0, 2, " m")
        self.stability_combo = self._combo(list("ABCDEF"), 3)
        self.wind_reference_height_spin = self._spin(
            10.0, 0.01, 100000.0, 2, " m")
        self.wind_exposure_combo = self._combo([
            tr('Rugosa'), tr('Plana')], 0)
        model_form.addRow(tr('Emisión:'), emission_row)
        model_form.addRow(tr('Altura de la chimenea:'), self.height_spin)
        model_form.addRow(tr('Estabilidad:'), self.stability_combo)
        model_form.addRow(
            tr('Altura de medición del viento:'),
            self.wind_reference_height_spin)
        model_form.addRow(tr('Exposición:'), self.wind_exposure_combo)
        layout.addWidget(self._group(tr('Emisión y atmósfera'), model_form))

        wind_form = QFormLayout()
        self.wind_mode_combo = self._combo([
            tr('Constante'), tr('Predominante sintético'),
            tr('Aleatorio uniforme sintético'),
            tr('Tabla CSV de observaciones')], 0)
        self.wind_speed_spin = self._spin(5.0, 1e-6, 1000.0, 3, " m/s")
        self.wind_from_spin = self._spin(0.0, 0.0, 360.0, 1, "°")
        self.wind_mode_combo.currentIndexChanged.connect(self._sync_wind_controls)
        wind_form.addRow(tr('Modo:'), self.wind_mode_combo)
        wind_form.addRow(tr('Rapidez:'), self.wind_speed_spin)
        wind_form.addRow(tr('Dirección DESDE:'), self.wind_from_spin)

        csv_row = QHBoxLayout()
        self.csv_edit = QLineEdit()
        self._allow_narrow(self.csv_edit)
        self.csv_edit.setPlaceholderText(
            tr('CSV preparado para la simulación'))
        self.csv_button = QPushButton(tr('Preparar CSV…'))
        self.clear_csv_button = QPushButton(tr('Quitar'))
        self.csv_button.clicked.connect(self.choose_csv)
        self.clear_csv_button.clicked.connect(self.clear_csv)
        csv_row.addWidget(self.csv_edit)
        csv_row.addWidget(self.csv_button)
        csv_row.addWidget(self.clear_csv_button)
        wind_form.addRow(tr('Tabla:'), csv_row)
        csv_help = QLabel(tr(
            'Selecciona un CSV con fecha, dirección y rapidez. El asistente '
            'permite asignar columnas, formato, zona horaria, unidades, '
            'convención DESDE/HACIA y códigos especiales.'))
        csv_help.setWordWrap(True)
        wind_form.addRow("", csv_help)
        layout.addWidget(self._group(tr('Viento'), wind_form))

        grid_form = QFormLayout()
        self.width_spin = self._spin(10000.0, 1.0, 100000.0, 0, " m")
        self.domain_height_spin = self._spin(
            10000.0, 1.0, 100000.0, 0, " m")
        self.resolution_spin = self._spin(50.0, 0.01, 100000.0, 2, " m")
        self.domain_policy_combo = self._combo([
            tr('Fijo'), tr('Extender lados que alcanzan el borde')], 0)
        grid_form.addRow(tr('Ancho:'), self.width_spin)
        grid_form.addRow(tr('Alto:'), self.domain_height_spin)
        grid_form.addRow(tr('Resolución:'), self.resolution_spin)
        grid_form.addRow(tr('Dominio:'), self.domain_policy_combo)
        layout.addWidget(self._group(tr('Grilla'), grid_form))
        self._sync_wind_controls()

        output_form = QFormLayout()
        self.scenario_edit = QLineEdit("simulacion_gaussiana")
        self._allow_narrow(self.scenario_edit)
        self.output_dir_edit = QLineEdit(
            QgsProject.instance().homePath() or
            str(Path.home() / "GaussianQGIS"))
        self._allow_narrow(self.output_dir_edit)
        self.output_dir_button = QPushButton(tr('Carpeta…'))
        self.output_dir_button.clicked.connect(self.choose_output_directory)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(self.output_dir_button)
        output_form.addRow(tr('Nombre del caso:'), self.scenario_edit)
        output_form.addRow(tr('Guardar en:'), output_row)
        self.concentration_unit_combo = self._combo(
            ["kg/m³", "g/m³", "mg/m³", "µg/m³"], 3)
        self.contour_minimum_spin = self._spin(1.0, 1e-12, 1e12, 12)
        output_form.addRow(tr('Concentración:'), self.concentration_unit_combo)
        output_form.addRow(tr('Isolínea mínima:'), self.contour_minimum_spin)
        layout.addWidget(self._group(tr('Resultados'), output_form))

        base_note = QLabel(
            tr('La ejecución directa usa estos valores. El formulario completo permite ingresar isolíneas manuales y destinos individuales.'))
        base_note.setWordWrap(True)
        layout.addWidget(base_note)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.open_button = QPushButton(tr('Revisar todos los parámetros…'))
        self.open_button.clicked.connect(self.open_algorithm)
        self.run_button = QPushButton(tr('Ejecutar y cargar capas'))
        self.run_button.clicked.connect(self.start_execution)
        self.cancel_button = QPushButton(tr('Cancelar cálculo'))
        self.cancel_button.clicked.connect(self.cancel_execution)
        self.cancel_button.setEnabled(False)
        scenario_buttons = QHBoxLayout()
        self.save_scenario_button = QPushButton(tr('Guardar escenario…'))
        self.load_scenario_button = QPushButton(tr('Abrir escenario…'))
        self.save_scenario_button.clicked.connect(self.choose_save_scenario)
        self.load_scenario_button.clicked.connect(self.choose_load_scenario)
        scenario_buttons.addWidget(self.save_scenario_button)
        scenario_buttons.addWidget(self.load_scenario_button)
        layout.addLayout(scenario_buttons)
        layout.addWidget(self.open_button)
        layout.addWidget(self.run_button)
        layout.addWidget(self.cancel_button)
        layout.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.setWidget(scroll)

    def start_capture(self):
        self.previous_map_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.map_tool)
        self.status_label.setText(tr('Haz clic en el mapa para ubicar la fuente.'))

    def _canvas_clicked(self, point, button):
        del button
        crs = self.canvas.mapSettings().destinationCrs()
        self.set_source(point, crs)
        if self.previous_map_tool is not None:
            self.canvas.setMapTool(self.previous_map_tool)
        else:
            self.canvas.unsetMapTool(self.map_tool)
        self.previous_map_tool = None

    def use_canvas_center(self):
        crs = self.canvas.mapSettings().destinationCrs()
        if crs.isValid():
            self.set_source(self.canvas.center(), crs)
        else:
            self.status_label.setText(tr('El lienzo necesita un CRS válido.'))

    def set_source(self, point, crs):
        """Set and normalize a source selected in any valid QGIS canvas CRS."""
        if not crs.isValid():
            raise ValueError(tr('El punto necesita un CRS válido'))
        point = QgsPointXY(point)
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        wgs84_point = point
        if crs != wgs84:
            transform = QgsCoordinateTransform(crs, wgs84,
                                               QgsProject.instance())
            wgs84_point = transform.transform(point)
        located = locate_source_coordinates(
            wgs84_point.x(), wgs84_point.y(), input_crs="EPSG:4326")
        self.source_point = point
        self.source_crs = QgsCoordinateReferenceSystem(crs)
        self.wgs84_point = QgsPointXY(wgs84_point)
        displays = (
            (self.original_edit, "{:.8f}, {:.8f} · {}".format(
                point.x(), point.y(), crs.authid() or crs.description())),
            (self.wgs84_edit,
             "lon {:.8f}, lat {:.8f} · EPSG:4326".format(
                 wgs84_point.x(), wgs84_point.y())),
            (self.calculation_edit, "E {:.3f}, N {:.3f} · {}".format(
                located.easting_m, located.northing_m,
                located.crs.to_string())),
        )
        for widget, value in displays:
            widget.setText(value)
            widget.setToolTip(value)
            widget.setCursorPosition(0)
        self.status_label.setText(
            tr('Fuente preparada. Revisa las coordenadas antes de simular.'))

    def choose_csv(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, tr('Seleccionar tabla de viento'), str(Path.home()),
            "CSV/TSV (*.csv *.tsv *.txt)")
        if filename:
            try:
                dialog = WindCsvImportDialog(filename, self)
                if dialog.exec() != QDialog.Accepted:
                    return
                self.csv_edit.setText(str(dialog.output_path))
                self.wind_original_path = str(Path(filename).resolve())
                self.wind_import_summary = dialog.summary.as_dict()
                self.wind_mode_combo.setCurrentIndex(3)
                self.status_label.setText(tr(
                    'Viento preparado: {} filas válidas; {} calmas, {} variables y {} ausentes excluidas.')
                    .format(dialog.summary.rows,
                            dialog.summary.excluded_calm_rows,
                            dialog.summary.excluded_variable_rows,
                            dialog.summary.excluded_missing_rows))
            except Exception as error:
                QMessageBox.warning(self, tr('Tabla de viento'), str(error))

    def clear_csv(self):
        self.csv_edit.clear()
        self.wind_import_summary = None
        self.wind_original_path = None
        if self.wind_mode_combo.currentIndex() == 3:
            self.wind_mode_combo.setCurrentIndex(0)

    def choose_output_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, tr('Carpeta para las simulaciones'),
            self.output_dir_edit.text().strip() or str(Path.home()))
        if directory:
            self.output_dir_edit.setText(directory)

    def _sync_wind_controls(self):
        mode = self.wind_mode_combo.currentIndex()
        table_mode = mode == 3
        self.wind_speed_spin.setEnabled(not table_mode)
        self.wind_from_spin.setEnabled(mode in (0, 1))
        self.csv_edit.setEnabled(table_mode)
        self.csv_button.setEnabled(table_mode)
        self.clear_csv_button.setEnabled(table_mode)
        if table_mode:
            self.domain_policy_combo.setCurrentIndex(0)
        self.domain_policy_combo.setEnabled(not table_mode)

    def algorithm_parameters(self):
        """Return safe prefilled parameters for the standard Processing dialog."""
        if self.wgs84_point is None:
            raise ValueError(tr('Seleccione primero la ubicación de la fuente'))
        parameters = {
            "SOURCE": "{:.12g},{:.12g} [EPSG:4326]".format(
                self.wgs84_point.x(), self.wgs84_point.y()),
            "EMISSION": self.emission_spin.value(),
            "EMISSION_UNIT": self.emission_unit_combo.currentIndex(),
            "WIND_MODE": self.wind_mode_combo.currentIndex(),
            "WIND_SPEED": self.wind_speed_spin.value(),
            "WIND_FROM": self.wind_from_spin.value(),
            "EFFECTIVE_HEIGHT": self.height_spin.value(),
            "STABILITY": self.stability_combo.currentIndex(),
            "WIND_REFERENCE_HEIGHT":
                self.wind_reference_height_spin.value(),
            "WIND_EXPOSURE": self.wind_exposure_combo.currentIndex(),
            "WIDTH": self.width_spin.value(),
            "HEIGHT": self.domain_height_spin.value(),
            "RESOLUTION": self.resolution_spin.value(),
            "DOMAIN_POLICY": self.domain_policy_combo.currentIndex(),
            "CONCENTRATION_UNIT":
                self.concentration_unit_combo.currentIndex(),
            "CONTOUR_MODE": 0,
            "CONTOUR_MINIMUM": self.contour_minimum_spin.value(),
        }
        csv_path = self.csv_edit.text().strip()
        if parameters["WIND_MODE"] == 3:
            if not csv_path:
                raise ValueError(tr('Seleccione un CSV para el modo tabla'))
            path = Path(csv_path).expanduser()
            if not path.is_file():
                raise ValueError(tr('No existe el CSV de viento seleccionado'))
            parameters.update({"WIND_FILE": str(path), "DOMAIN_POLICY": 0})
        return parameters

    @staticmethod
    def _safe_name(name):
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._-")
        if not safe:
            raise ValueError(tr('Ingrese un nombre válido para el caso'))
        return safe

    def _parameter_widgets(self):
        return {
            "EMISSION": self.emission_spin,
            "EMISSION_UNIT": self.emission_unit_combo,
            "WIND_MODE": self.wind_mode_combo,
            "WIND_SPEED": self.wind_speed_spin,
            "WIND_FROM": self.wind_from_spin,
            "EFFECTIVE_HEIGHT": self.height_spin,
            "STABILITY": self.stability_combo,
            "WIND_REFERENCE_HEIGHT": self.wind_reference_height_spin,
            "WIND_EXPOSURE": self.wind_exposure_combo,
            "WIDTH": self.width_spin,
            "HEIGHT": self.domain_height_spin,
            "RESOLUTION": self.resolution_spin,
            "DOMAIN_POLICY": self.domain_policy_combo,
            "CONCENTRATION_UNIT": self.concentration_unit_combo,
            "CONTOUR_MINIMUM": self.contour_minimum_spin,
        }

    def save_scenario(self, filename, parameters=None):
        """Write a portable input record and a checked copy of the wind CSV."""
        parameters = dict(parameters or self.algorithm_parameters())
        for key in ("OUTPUT", "ISOLINES", "SOURCE_OUTPUT", "WIND_ROSE"):
            parameters.pop(key, None)
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        wind_hash = None
        if parameters["WIND_MODE"] == 3:
            original = Path(parameters["WIND_FILE"])
            copied = path.with_name(path.stem + "_viento.csv")
            if original.resolve() != copied.resolve():
                shutil.copyfile(original, copied)
            wind_hash = hashlib.sha256(copied.read_bytes()).hexdigest()
            parameters["WIND_FILE"] = copied.name
        document = {
            "schema_version": 2,
            "plugin_version": "0.14.0",
            "algorithm": self.ALGORITHM_ID,
            "name": self.scenario_edit.text().strip(),
            "source_input": {
                "x": self.source_point.x(), "y": self.source_point.y(),
                "crs": self.source_crs.toWkt()},
            "parameters": parameters,
            "wind_sha256": wind_hash,
            "wind_import": ({"source_file": self.wind_original_path,
                             "summary": self.wind_import_summary}
                            if self.wind_import_summary else None),
            "output_base": self.output_dir_edit.text().strip(),
        }
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        temporary.replace(path)
        return path

    def load_scenario(self, filename):
        """Validate all inputs before replacing the panel's current scenario."""
        if self.active_task is not None:
            raise ValueError(tr('Espere a que termine el cálculo antes de abrir un escenario'))
        path = Path(filename)
        document = json.loads(path.read_text(encoding="utf-8"))
        if (document.get("schema_version") not in (1, 2) or
                document.get("algorithm") != self.ALGORITHM_ID):
            raise ValueError(tr('Formato de escenario incompatible'))
        self._safe_name(document["name"])
        parameters = dict(document["parameters"])
        # Extra parameters from earlier schemas are ignored. All scenarios use
        # the Masters 2008 / Martin 1976 formulation.
        parameters.setdefault("WIND_REFERENCE_HEIGHT", 10.0)
        parameters.setdefault("WIND_EXPOSURE", 0)
        for key, widget in self._parameter_widgets().items():
            value = parameters[key]
            if isinstance(widget, QComboBox):
                if type(value) is not int or not 0 <= value < widget.count():
                    raise ValueError(tr('Opción inválida: ') + key)
            elif (isinstance(value, bool) or not isinstance(value, (int, float)) or
                  not math.isfinite(value) or
                  not widget.minimum() <= value <= widget.maximum()):
                raise ValueError(tr('Valor fuera de rango: ') + key)
        if parameters.get("CONTOUR_MODE") != 0:
            raise ValueError(tr('Este panel abre escenarios con isolíneas automáticas'))
        # Scenarios written through 0.9.1 used index 1 for CSV.
        if (parameters.get("WIND_MODE") == 1 and
                parameters.get("WIND_FILE")):
            parameters["WIND_MODE"] = 3
        if parameters.get("WIND_MODE") not in (0, 1, 2, 3):
            raise ValueError(tr('Modo de viento incompatible'))
        csv_path = ""
        if parameters["WIND_MODE"] == 3:
            csv_path = Path(parameters["WIND_FILE"])
            if not csv_path.is_absolute():
                csv_path = path.parent / csv_path
            if (not csv_path.is_file() or
                    hashlib.sha256(csv_path.read_bytes()).hexdigest() !=
                    document.get("wind_sha256")):
                raise ValueError(tr('El CSV falta o cambió desde que se guardó el escenario'))
            if parameters["DOMAIN_POLICY"] != 0:
                raise ValueError(tr('El viento CSV necesita dominio fijo'))
        source = document["source_input"]
        if any(not isinstance(source[key], (int, float)) or
               not math.isfinite(source[key]) for key in ("x", "y")):
            raise ValueError(tr('Coordenadas inválidas'))
        crs = QgsCoordinateReferenceSystem()
        crs.createFromWkt(source["crs"])
        self.set_source(QgsPointXY(source["x"], source["y"]), crs)
        for key, widget in self._parameter_widgets().items():
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(parameters[key])
            else:
                widget.setValue(parameters[key])
        self.csv_edit.setText(str(csv_path))
        wind_import = document.get("wind_import") or {}
        self.wind_original_path = wind_import.get("source_file")
        self.wind_import_summary = wind_import.get("summary")
        self._sync_wind_controls()
        self.scenario_edit.setText(document["name"])
        self.output_dir_edit.setText(document.get("output_base") or str(path.parent))
        self.status_label.setText(tr('Escenario recuperado. Revisa los parámetros y ejecuta.'))

    def choose_save_scenario(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, tr('Guardar escenario'), "escenario.json", "JSON (*.json)")
        if filename:
            try:
                self.save_scenario(filename)
                self.status_label.setText(tr('Escenario guardado: ') + filename)
            except Exception as error:
                QMessageBox.warning(self, tr('Escenario'), str(error))

    def choose_load_scenario(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, tr('Abrir escenario'), self.output_dir_edit.text(), "JSON (*.json)")
        if filename:
            try:
                self.load_scenario(filename)
            except Exception as error:
                QMessageBox.warning(self, tr('Escenario'), str(error))

    def execution_parameters(self):
        """Create a fresh directory and explicit outputs for a direct run."""
        parameters = self.algorithm_parameters()
        base_text = self.output_dir_edit.text().strip()
        if not base_text:
            raise ValueError(tr('Seleccione una carpeta para guardar resultados'))
        base = Path(base_text).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_name(self.scenario_edit.text())
        target = base / safe_name
        suffix = 0
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        while target.exists() and any(target.iterdir()):
            suffix += 1
            target = base / "{}_{}_{}".format(safe_name, stamp, suffix)
        target.mkdir(parents=True, exist_ok=True)
        parameters.update({
            "OUTPUT": str(target / "concentracion.tif"),
            "ISOLINES": str(target / "isolineas.gpkg"),
            "SOURCE_OUTPUT": str(target / "fuente.gpkg"),
        })
        if parameters["WIND_MODE"] in (1, 2, 3):
            parameters["WIND_ROSE"] = str(target / "rosa_vientos.png")
        return parameters, target, self.scenario_edit.text().strip()

    def open_algorithm(self):
        try:
            parameters = self.algorithm_parameters()
            import processing
            processing.execAlgorithmDialog(self.ALGORITHM_ID, parameters)
        except Exception as error:
            QMessageBox.warning(self, tr('Pluma Gaussiana Educativa'), str(error))

    def start_execution(self):
        if self.active_task is not None:
            return
        try:
            parameters, target, scenario = self.execution_parameters()
            scenario_file = self.save_scenario(target / "escenario.json", parameters)
            if parameters["WIND_MODE"] == 3:
                parameters["WIND_FILE"] = str(target / "escenario_viento.csv")
            algorithm = QgsApplication.processingRegistry().algorithmById(
                self.ALGORITHM_ID)
            if algorithm is None:
                raise RuntimeError(tr('El algoritmo gaussiano no está registrado'))
            context = QgsProcessingContext()
            context.setProject(QgsProject.instance())
            context.setTransformContext(QgsProject.instance().transformContext())
            feedback = QgsProcessingFeedback()
            task = QgsProcessingAlgRunnerTask(
                algorithm, parameters, context, feedback)
            feedback.progressChanged.connect(
                lambda value: self.progress_bar.setValue(round(value)))
            task.executed.connect(self._execution_finished)
            self.active_task = task
            self.task_context = context
            self.task_feedback = feedback
            self.running_scenario = scenario
            self.running_scenario_file = scenario_file
            self.running_unit_index = \
                self.concentration_unit_combo.currentIndex()
            self.running_unit_label = \
                self.concentration_unit_combo.currentText()
            self._set_running(True)
            self.status_label.setText(
                tr('Calculando {}… Resultados: {}').format(scenario, target))
            QgsApplication.taskManager().addTask(task)
        except Exception as error:
            QMessageBox.warning(self, tr('Pluma Gaussiana Educativa'), str(error))

    def _set_running(self, running):
        self.run_button.setEnabled(not running)
        self.open_button.setEnabled(not running)
        self.capture_button.setEnabled(not running)
        self.center_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.load_scenario_button.setEnabled(not running)
        self.save_scenario_button.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)

    def cancel_execution(self):
        if self.active_task is not None:
            self.status_label.setText(tr('Cancelando el cálculo…'))
            self.active_task.cancel()

    def _execution_finished(self, successful, results):
        was_canceled = (self.task_feedback is not None and
                        self.task_feedback.isCanceled())
        try:
            if self.running_scenario_file is not None:
                document = json.loads(self.running_scenario_file.read_text(encoding="utf-8"))
                document["execution"] = {
                    "status": "completed" if successful else
                        ("canceled" if was_canceled else "failed"),
                    "results": results,
                }
                self.running_scenario_file.write_text(
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
            if successful:
                self._load_results(results)
                self.status_label.setText(
                    tr('Completado. Máximo: {:.6g}; borde: {:.6g} {}. {}').format(
                        float(results.get("MAXIMUM", 0.0)),
                        float(results.get("BORDER_MAXIMUM", 0.0)),
                        self.running_unit_label,
                        results.get("DOMAIN_STATUS", "")))
            elif was_canceled:
                self.status_label.setText(tr('Cálculo cancelado por el usuario.'))
            else:
                self.status_label.setText(
                    tr('El cálculo terminó con error. Revisa el registro de tareas.'))
        except Exception as error:
            self.status_label.setText(
                tr('El cálculo terminó, pero no se pudieron cargar las capas: {}').format(
                    error))
        finally:
            self._set_running(False)
            self.active_task = None
            self.task_context = None
            self.task_feedback = None

    def _load_results(self, results):
        raster = QgsRasterLayer(str(results["OUTPUT"]), tr('Concentración'))
        isolines = QgsVectorLayer(str(results["ISOLINES"]), tr('Isolíneas'), "ogr")
        source = QgsVectorLayer(str(results["SOURCE_OUTPUT"]), tr('Fuente'), "ogr")
        invalid = [name for name, layer in (
            (tr('ráster'), raster), (tr('isolíneas'), isolines), (tr('fuente'), source))
                   if not layer.isValid()]
        if invalid:
            raise RuntimeError(tr('salida inválida: ') + ", ".join(invalid))
        levels = sorted({float(feature["concentration"])
                         for feature in isolines.getFeatures()})
        maximum = float(results["MAXIMUM"])
        threshold = 1e-10 * 10.0 ** (3 * self.running_unit_index)
        style_raster(raster, levels=levels, maximum=maximum,
                     transparent_below=threshold,
                     unit_label=self.running_unit_label)
        style_isolines(isolines, levels=levels,
                       unit_label=self.running_unit_label)
        style_source(source)
        project = QgsProject.instance()
        group = project.layerTreeRoot().insertGroup(
            0, tr('Pluma · {} · {}').format(
                self.running_scenario, datetime.now().strftime("%H:%M:%S")))
        for layer in (source, isolines, raster):
            project.addMapLayer(layer, False)
            group.addLayer(layer)
        extent = raster.extent()
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if canvas_crs != raster.crs():
            transform = QgsCoordinateTransform(raster.crs(), canvas_crs, project)
            extent = transform.transformBoundingBox(extent)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def cleanup(self):
        if self.active_task is not None:
            self.active_task.cancel()
        if self.canvas.mapTool() is self.map_tool:
            if self.previous_map_tool is not None:
                self.canvas.setMapTool(self.previous_map_tool)
            else:
                self.canvas.unsetMapTool(self.map_tool)
        self.previous_map_tool = None
