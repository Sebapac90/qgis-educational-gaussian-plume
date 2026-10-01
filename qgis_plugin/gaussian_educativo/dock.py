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

from qgis.PyQt.QtCore import Qt, QMetaType
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QListWidget, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QStackedWidget)
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsFeature, QgsField, QgsGeometry, QgsPointXY,
    QgsProcessingAlgRunnerTask,
    QgsProcessingContext, QgsProcessingFeedback, QgsProject, QgsRasterLayer,
    QgsVectorLayer)
from qgis.gui import QgsDockWidget, QgsMapToolEmitPoint

from .gaussian_spatial import (locate_source_coordinates,
                               maximum_geodesic_separation_m)
from .gaussian_units import canonical_unit, emission_to_kg_s
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


class BriggsParametersDialog(QDialog):
    """Keep optional Briggs inputs out of the main simulation dock."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Configurar elevación Briggs'))
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        note = QLabel(tr(
            'Estos parámetros se usan solo con «Elevación de la pluma». La rapidez '
            'del viento y la clase de estabilidad se toman del panel principal. '
            'Para las clases E–F indique el gradiente vertical ambiente.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.stack_diameter_spin = self._spin(2.0, 1e-6, 10000.0, 3, " m")
        self.exit_velocity_spin = self._spin(10.0, 1e-6, 10000.0, 3, " m/s")
        self.stack_temperature_spin = self._spin(
            126.85, -273.14, 5000.0, 2, " °C")
        self.ambient_temperature_spin = self._spin(
            26.85, -273.14, 1000.0, 2, " °C")
        self.ambient_gradient_spin = self._spin(
            2.0, -9.999999, 1000.0, 3, " °C/km")
        self.ambient_gradient_label = QLabel(tr('Gradiente para E–F:'))
        self.stack_tip_downwash_combo = QComboBox()
        self.stack_tip_downwash_combo.addItems(
            [tr('Desactivado'), tr('Activado')])
        form.addRow(tr('Diámetro interior:'), self.stack_diameter_spin)
        form.addRow(tr('Velocidad de salida:'), self.exit_velocity_spin)
        form.addRow(tr('Temperatura del gas:'), self.stack_temperature_spin)
        form.addRow(tr('Temperatura ambiente:'), self.ambient_temperature_spin)
        form.addRow(self.ambient_gradient_label, self.ambient_gradient_spin)
        form.addRow(tr('Descenso en la boca:'), self.stack_tip_downwash_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_stability_class(self, stability_class):
        """The ambient vertical gradient is only used for stable classes E–F."""
        enabled = stability_class in ('E', 'F')
        self.ambient_gradient_label.setEnabled(enabled)
        self.ambient_gradient_spin.setEnabled(enabled)

    @staticmethod
    def _spin(value, minimum, maximum, decimals=3, suffix=""):
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        return widget


class SourceTableDialog(QDialog):
    """Edit one source at a time while keeping scenario inputs separate."""

    def __init__(self, rows, emission_unit, height_mode, wind_summary,
                 parent=None, initial_index=0):
        super().__init__(parent)
        self.setWindowTitle(tr('Fuentes emisoras'))
        self.resize(760, 500)
        self.emission_unit = emission_unit
        self.height_mode = height_mode
        self._source_rows = [dict(row) for row in rows]
        self._current_index = -1
        self.edit_wind_requested = False
        self.rows = None
        layout = QVBoxLayout(self)
        note = QLabel(tr('Selecciona una fuente y modifica sus datos.'))
        note.setWordWrap(True)
        layout.addWidget(note)

        content = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel(tr('Fuentes:')))
        self.source_list = QListWidget()
        self.source_list.setMinimumWidth(190)
        left.addWidget(self.source_list)
        source_buttons = QHBoxLayout()
        self.duplicate_button = QPushButton(tr('Duplicar'))
        self.remove_button = QPushButton(tr('Eliminar'))
        self.duplicate_button.clicked.connect(self._add_copy)
        self.remove_button.clicked.connect(self._remove_selected)
        source_buttons.addWidget(self.duplicate_button)
        source_buttons.addWidget(self.remove_button)
        left.addLayout(source_buttons)
        content.addLayout(left, 1)

        details = QVBoxLayout()
        basic_form = QFormLayout()
        self.name_edit = QLineEdit()
        self.longitude_spin = self._spin(0.0, -180.0, 180.0, 8, "°")
        self.latitude_spin = self._spin(0.0, -90.0, 90.0, 8, "°")
        self.emission_spin = self._spin(0.0, 0.0, 1e12, 8,
                                        " " + emission_unit)
        self.height_spin = self._spin(50.0, 1e-6, 100000.0, 3, " m")
        basic_form.addRow(tr('Nombre:'), self.name_edit)
        basic_form.addRow(tr('Longitud WGS84:'), self.longitude_spin)
        basic_form.addRow(tr('Latitud WGS84:'), self.latitude_spin)
        basic_form.addRow(tr('Emisión:'), self.emission_spin)
        basic_form.addRow((tr('Altura efectiva:') if height_mode == 1 else
                           tr('Altura de chimenea:')), self.height_spin)
        details.addWidget(self._group(tr('Fuente seleccionada'), basic_form))

        briggs_form = QFormLayout()
        self.diameter_spin = self._spin(2.0, 1e-6, 10000.0, 3, " m")
        self.exit_velocity_spin = self._spin(
            10.0, 1e-6, 10000.0, 3, " m/s")
        self.temperature_spin = self._spin(
            126.85, -273.14, 5000.0, 2, " °C")
        briggs_form.addRow(tr('Diámetro interior:'), self.diameter_spin)
        briggs_form.addRow(tr('Velocidad de salida:'),
                           self.exit_velocity_spin)
        briggs_form.addRow(tr('Temperatura del gas:'), self.temperature_spin)
        self.briggs_group = self._group(
            tr('Elevación de la pluma · fuente seleccionada'), briggs_form)
        self.briggs_group.setVisible(height_mode == 2)
        details.addWidget(self.briggs_group)

        weather_layout = QVBoxLayout()
        self.wind_summary_label = QLabel(tr(
            'Meteorología compartida; la rapidez se ajusta a la altura de cada '
            'chimenea.') + '\n' + wind_summary)
        self.wind_summary_label.setWordWrap(True)
        weather_layout.addWidget(self.wind_summary_label)
        self.edit_wind_button = QPushButton(
            tr('Guardar fuentes y modificar viento…'))
        self.edit_wind_button.clicked.connect(self._request_wind_edit)
        weather_layout.addWidget(self.edit_wind_button)
        weather_group = self._group(tr('Meteorología común'), weather_layout)
        details.addWidget(weather_group)
        details.addStretch(1)
        content.addLayout(details, 2)
        layout.addLayout(content)

        for row in self._source_rows:
            self.source_list.addItem(row.get(
                'name', tr('Fuente {}').format(self.source_list.count() + 1)))
        self.source_list.currentRowChanged.connect(self._select_source)
        self.name_edit.textChanged.connect(self._update_current_name)
        if self._source_rows:
            self.source_list.setCurrentRow(max(
                0, min(initial_index, len(self._source_rows) - 1)))
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _unit_factor(unit):
        return emission_to_kg_s(1.0, canonical_unit(unit))

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
    def _group(title, contents):
        group = QGroupBox(title)
        group.setLayout(contents)
        return group

    def _save_current(self):
        if not 0 <= self._current_index < len(self._source_rows):
            return
        # keyboardTracking is disabled to keep the panel responsive. Commit
        # any text still being edited before changing sources or accepting.
        for widget in (self.longitude_spin, self.latitude_spin,
                       self.emission_spin, self.height_spin,
                       self.diameter_spin, self.exit_velocity_spin,
                       self.temperature_spin):
            widget.interpretText()
        factor = self._unit_factor(self.emission_unit)
        self._source_rows[self._current_index].update({
            'name': self.name_edit.text().strip() or
                    tr('Fuente {}').format(self._current_index + 1),
            'longitude': self.longitude_spin.value(),
            'latitude': self.latitude_spin.value(),
            'emission_kg_s': self.emission_spin.value() * factor,
            'height_m': self.height_spin.value(),
            'diameter_m': self.diameter_spin.value(),
            'exit_velocity_m_s': self.exit_velocity_spin.value(),
            'temperature_c': self.temperature_spin.value(),
        })

    def _select_source(self, index):
        self._save_current()
        self._current_index = index
        enabled = 0 <= index < len(self._source_rows)
        for widget in (self.name_edit, self.longitude_spin,
                       self.latitude_spin, self.emission_spin,
                       self.height_spin, self.diameter_spin,
                       self.exit_velocity_spin, self.temperature_spin):
            widget.setEnabled(enabled)
        self.remove_button.setEnabled(enabled and len(self._source_rows) > 1)
        if not enabled:
            return
        row = self._source_rows[index]
        factor = self._unit_factor(self.emission_unit)
        self.name_edit.setText(row.get(
            'name', tr('Fuente {}').format(index + 1)))
        self.longitude_spin.setValue(float(row.get('longitude', 0.0)))
        self.latitude_spin.setValue(float(row.get('latitude', 0.0)))
        self.emission_spin.setValue(
            float(row.get('emission_kg_s', 0.0)) / factor)
        self.height_spin.setValue(float(row.get('height_m', 50.0)))
        self.diameter_spin.setValue(float(row.get('diameter_m', 2.0)))
        self.exit_velocity_spin.setValue(
            float(row.get('exit_velocity_m_s', 10.0)))
        self.temperature_spin.setValue(
            float(row.get('temperature_c', 126.85)))

    def _update_current_name(self, text):
        if 0 <= self._current_index < self.source_list.count():
            self.source_list.item(self._current_index).setText(
                text.strip() or tr('Fuente {}').format(
                    self._current_index + 1))

    def _add_copy(self):
        self._save_current()
        source = (dict(self._source_rows[self._current_index])
                  if self._source_rows else {})
        index = len(self._source_rows)
        source['name'] = tr('Fuente {}').format(index + 1)
        self._source_rows.append(source)
        self.source_list.addItem(source['name'])
        self.source_list.setCurrentRow(index)

    def _remove_selected(self):
        index = self.source_list.currentRow()
        if index < 0 or len(self._source_rows) <= 1:
            return
        self._current_index = -1
        self._source_rows.pop(index)
        self.source_list.takeItem(index)
        self.source_list.setCurrentRow(min(index, len(self._source_rows) - 1))

    def _request_wind_edit(self):
        if self._validate_rows():
            self.edit_wind_requested = True
            self.accept()

    def _validate_rows(self):
        self._save_current()
        if not self._source_rows:
            QMessageBox.warning(self, tr('Fuentes'),
                                tr('Ingrese al menos una fuente.'))
            return False
        for index, row in enumerate(self._source_rows):
            row['name'] = row.get('name') or tr('Fuente {}').format(index + 1)
            values = (row['longitude'], row['latitude'],
                      row['emission_kg_s'], row['height_m'],
                      row['diameter_m'], row['exit_velocity_m_s'],
                      row['temperature_c'])
            if any(not math.isfinite(float(value)) for value in values):
                QMessageBox.warning(
                    self, tr('Fuentes'),
                    tr('Todas las fuentes deben contener valores válidos.'))
                return False
        self.rows = [dict(row) for row in self._source_rows]
        return True

    def _validate_and_accept(self):
        if self._validate_rows():
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
        self.sources = []
        self._source_layer = None
        self.pending_multiple_capture = False
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
        self._update_source_count()
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
        self.emission_unit_combo.currentIndexChanged.connect(
            self._invalidate_source_layer)
        emission_row.addWidget(self.emission_spin)
        emission_row.addWidget(self.emission_unit_combo)
        self.stack_height_spin = self._spin(50.0, 0.0, 100000.0, 2, " m")
        self.manual_effective_height_spin = self._spin(
            50.0, 0.0, 100000.0, 2, " m")
        # Kept as an alias for external code that sets the physical stack height.
        self.height_spin = self.stack_height_spin
        self.height_inputs = QStackedWidget()
        self.height_inputs.addWidget(self.stack_height_spin)
        self.height_inputs.addWidget(self.manual_effective_height_spin)
        self.height_mode_combo = self._combo([
            tr('Altura de chimenea (sin elevación)'),
            tr('Altura efectiva ingresada'),
            tr('Elevación de la pluma')], 0)
        self.briggs_dialog = BriggsParametersDialog(self)
        self.stack_diameter_spin = self.briggs_dialog.stack_diameter_spin
        self.exit_velocity_spin = self.briggs_dialog.exit_velocity_spin
        self.stack_temperature_spin = self.briggs_dialog.stack_temperature_spin
        self.ambient_temperature_spin = self.briggs_dialog.ambient_temperature_spin
        self.ambient_gradient_spin = self.briggs_dialog.ambient_gradient_spin
        self.stack_tip_downwash_combo = (
            self.briggs_dialog.stack_tip_downwash_combo)
        self.briggs_button = QPushButton(tr('Configurar Briggs…'))
        self.briggs_button.clicked.connect(self.configure_briggs)
        self.height_mode_combo.currentIndexChanged.connect(
            self._sync_height_controls)
        self.stability_combo = self._combo(list("ABCDEF"), 3)
        self.stability_combo.currentTextChanged.connect(
            self._sync_briggs_stability)
        self.wind_reference_height_spin = self._spin(
            10.0, 0.01, 100000.0, 2, " m")
        self.wind_exposure_combo = self._combo([
            tr('Rugosa'), tr('Plana')], 0)
        model_form.addRow(tr('Emisión:'), emission_row)
        model_form.addRow(tr('Tratamiento de la altura:'),
                          self.height_mode_combo)
        self.height_label = QLabel()
        model_form.addRow(self.height_label, self.height_inputs)
        model_form.addRow("", self.briggs_button)
        model_form.addRow(tr('Estabilidad:'), self.stability_combo)
        model_form.addRow(
            tr('Altura de medición del viento:'),
            self.wind_reference_height_spin)
        model_form.addRow(tr('Exposición:'), self.wind_exposure_combo)
        layout.addWidget(self._group(tr('Emisión y atmósfera'), model_form))
        self._sync_height_controls()
        self._sync_briggs_stability()

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
        self.wind_group = self._group(tr('Viento'), wind_form)
        layout.addWidget(self.wind_group)

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

        multi_layout = QVBoxLayout()
        multi_note = QLabel(tr(
            'Opcional: parte de la fuente y parámetros actuales para crear '
            'una tabla con varias chimeneas.'))
        multi_note.setWordWrap(True)
        multi_layout.addWidget(multi_note)
        multi_buttons = QHBoxLayout()
        self.manage_sources_button = QPushButton(tr('Agregar multifuente…'))
        self.add_more_source_button = QPushButton(
            tr('Añadir otra desde el mapa'))
        self.clear_sources_button = QPushButton(tr('Volver a fuente única'))
        self.manage_sources_button.clicked.connect(
            self.configure_multiple_sources)
        self.add_more_source_button.clicked.connect(
            self.add_another_source_from_map)
        self.clear_sources_button.clicked.connect(self.clear_sources)
        multi_buttons.addWidget(self.manage_sources_button)
        multi_buttons.addWidget(self.add_more_source_button)
        multi_buttons.addWidget(self.clear_sources_button)
        multi_layout.addLayout(multi_buttons)
        layout.addWidget(self._group(tr('Varias fuentes'), multi_layout))

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
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(body)
        self.setWidget(self.scroll)

    def start_capture(self):
        self.pending_multiple_capture = False
        self.previous_map_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.map_tool)
        self.status_label.setText(tr('Haz clic en el mapa para ubicar la fuente.'))

    def _canvas_clicked(self, point, button):
        del button
        crs = self.canvas.mapSettings().destinationCrs()
        if self.pending_multiple_capture:
            self.pending_multiple_capture = False
            self._finish_multiple_source_capture(point, crs)
        else:
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

    def _invalidate_source_layer(self, *unused):
        del unused
        self._source_layer = None

    def _update_source_count(self):
        self.manage_sources_button.setText(
            (tr('Modificar multifuente ({})…').format(len(self.sources))
             if self.sources else tr('Agregar multifuente…')))
        self.add_more_source_button.setVisible(bool(self.sources))
        self.clear_sources_button.setEnabled(bool(self.sources))

    def _current_source_row(self, name=None):
        if self.wgs84_point is None:
            raise ValueError(
                tr('Seleccione primero una ubicación en el mapa.'))
        return {
            'name': name or tr('Fuente 1'),
            'longitude': self.wgs84_point.x(),
            'latitude': self.wgs84_point.y(),
            'emission_kg_s': emission_to_kg_s(
                self.emission_spin.value(),
                self.emission_unit_combo.currentText()),
            'height_m': self._active_height_spin().value(),
            'diameter_m': self.stack_diameter_spin.value(),
            'exit_velocity_m_s': self.exit_velocity_spin.value(),
            'temperature_c': self.stack_temperature_spin.value(),
        }

    def add_current_source(self):
        """Compatibility helper; the visible workflow uses the table dialog."""
        if self.wgs84_point is None:
            QMessageBox.warning(self, tr('Fuentes'),
                                tr('Seleccione primero una ubicación en el mapa.'))
            return
        self.sources.append(self._current_source_row(
            tr('Fuente {}').format(len(self.sources) + 1)))
        self._invalidate_source_layer()
        self._update_source_count()
        self.status_label.setText(tr('Tabla de fuentes actualizada.'))

    def configure_multiple_sources(self):
        if self.sources:
            self._open_multiple_source_dialog(self.sources)
            return
        try:
            self._current_source_row()
        except ValueError as error:
            QMessageBox.warning(self, tr('Fuentes'), str(error))
            return
        self._start_multiple_source_capture(
            tr('Haz clic en el mapa para ubicar la segunda fuente.'))

    def add_another_source_from_map(self):
        if not self.sources:
            self.configure_multiple_sources()
            return
        self._start_multiple_source_capture(
            tr('Haz clic en el mapa para ubicar la nueva fuente.'))

    def _start_multiple_source_capture(self, message):
        self.pending_multiple_capture = True
        self.previous_map_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.map_tool)
        self.status_label.setText(message)

    def _finish_multiple_source_capture(self, point, crs):
        if not crs.isValid():
            QMessageBox.warning(self, tr('Fuentes'),
                                tr('El punto necesita un CRS válido'))
            return
        point = QgsPointXY(point)
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        if crs != wgs84:
            point = QgsCoordinateTransform(
                crs, wgs84, QgsProject.instance()).transform(point)
        if self.sources:
            initial_rows = [dict(row) for row in self.sources]
            new_source = dict(initial_rows[-1])
        else:
            first = self._current_source_row(tr('Fuente 1'))
            initial_rows = [first]
            new_source = dict(first)
        new_source.update({
            'name': tr('Fuente {}').format(len(initial_rows) + 1),
            'longitude': point.x(),
            'latitude': point.y(),
        })
        initial_rows.append(new_source)
        self._open_multiple_source_dialog(
            initial_rows, selected_index=len(initial_rows) - 1)

    def _open_multiple_source_dialog(self, initial_rows, selected_index=0):
        dialog = SourceTableDialog(
            initial_rows, self.emission_unit_combo.currentText(),
            self.height_mode_combo.currentIndex(), self._wind_summary(), self,
            initial_index=selected_index)
        if dialog.exec() == QDialog.Accepted:
            self.sources = dialog.rows
            self._invalidate_source_layer()
            self._update_source_count()
            self.status_label.setText(tr(
                'Multifuente activa con {} fuentes.').format(
                    len(self.sources)))
            if dialog.edit_wind_requested:
                self.scroll.ensureWidgetVisible(self.wind_group)
                (self.csv_button if self.wind_mode_combo.currentIndex() == 3
                 else self.wind_speed_spin).setFocus()
                self.status_label.setText(tr(
                    'Fuentes guardadas. Modifica el viento común y vuelve a '
                    'abrir multifuente si necesitas revisar las chimeneas.'))

    def _wind_summary(self):
        mode = self.wind_mode_combo.currentText()
        if self.wind_mode_combo.currentIndex() == 3:
            source = (Path(self.csv_edit.text()).name
                      if self.csv_edit.text() else tr('sin CSV'))
            detail = tr('Archivo: {}').format(source)
        elif self.wind_mode_combo.currentIndex() == 2:
            detail = tr('Rapidez de referencia: {:.3f} m/s').format(
                self.wind_speed_spin.value())
        else:
            detail = tr(
                'Rapidez de referencia: {:.3f} m/s · dirección DESDE: {:.1f}°'
            ).format(self.wind_speed_spin.value(), self.wind_from_spin.value())
        return tr('{} · {} · estabilidad {} · medición a {:.2f} m').format(
            mode, detail, self.stability_combo.currentText(),
            self.wind_reference_height_spin.value())

    def manage_sources(self):
        """Backward-compatible alias for tests and saved UI integrations."""
        self.configure_multiple_sources()

    def clear_sources(self):
        self.sources = []
        self._invalidate_source_layer()
        self._update_source_count()
        self.status_label.setText(tr(
            'Multifuente desactivada; se usará la fuente única actual.'))

    def _build_source_layer(self):
        if self._source_layer is not None:
            return self._source_layer
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326", tr('Fuentes de la simulación'), "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField('name', QMetaType.Type.QString, len=80),
            QgsField('emission', QMetaType.Type.Double),
            QgsField('height_m', QMetaType.Type.Double),
            QgsField('diameter_m', QMetaType.Type.Double),
            QgsField('exit_m_s', QMetaType.Type.Double),
            QgsField('temp_c', QMetaType.Type.Double),
        ])
        layer.updateFields()
        factor = emission_to_kg_s(
            1.0, self.emission_unit_combo.currentText())
        features = []
        for row in self.sources:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(
                row['longitude'], row['latitude'])))
            feature.setAttributes([
                row['name'], row['emission_kg_s'] / factor, row['height_m'],
                row['diameter_m'], row['exit_velocity_m_s'],
                row['temperature_c']])
            features.append(feature)
        if not provider.addFeatures(features):
            raise ValueError(tr('No se pudo preparar la capa de fuentes'))
        layer.updateExtents()
        self._source_layer = layer
        return layer

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

    def _sync_height_controls(self):
        mode = self.height_mode_combo.currentIndex()
        briggs = mode == 2
        self.height_inputs.setCurrentIndex(1 if mode == 1 else 0)
        self.height_label.setText(
            tr('Altura efectiva ingresada:') if mode == 1 else
            tr('Altura de la chimenea:'))
        self.briggs_button.setVisible(briggs)

    def _active_height_spin(self, mode=None):
        """Return the input whose physical meaning matches the selected mode."""
        mode = self.height_mode_combo.currentIndex() if mode is None else mode
        return self.manual_effective_height_spin if mode == 1 else self.stack_height_spin

    def _sync_briggs_stability(self):
        self.briggs_dialog.set_stability_class(
            self.stability_combo.currentText())

    def configure_briggs(self):
        previous = (
            self.stack_diameter_spin.value(), self.exit_velocity_spin.value(),
            self.stack_temperature_spin.value(),
            self.ambient_temperature_spin.value(),
            self.ambient_gradient_spin.value(),
            self.stack_tip_downwash_combo.currentIndex())
        if self.briggs_dialog.exec() == QDialog.Accepted:
            self.status_label.setText(tr('Parámetros Briggs actualizados.'))
        else:
            self.stack_diameter_spin.setValue(previous[0])
            self.exit_velocity_spin.setValue(previous[1])
            self.stack_temperature_spin.setValue(previous[2])
            self.ambient_temperature_spin.setValue(previous[3])
            self.ambient_gradient_spin.setValue(previous[4])
            self.stack_tip_downwash_combo.setCurrentIndex(previous[5])

    def algorithm_parameters(self):
        """Return safe prefilled parameters for the standard Processing dialog."""
        if self.wgs84_point is None:
            raise ValueError(tr('Seleccione primero la ubicación de la fuente'))
        if self.sources:
            maximum_distance = maximum_geodesic_separation_m(
                (row['longitude'], row['latitude']) for row in self.sources)
            domain_diagonal = math.hypot(
                self.width_spin.value(), self.domain_height_spin.value())
            if maximum_distance > domain_diagonal:
                raise ValueError(tr(
                    'El modo multifuente usa un único dominio local y una '
                    'meteorología común. Las fuentes seleccionadas no '
                    'caben en el dominio de {:.0f} × {:.0f} m. Agrupe '
                    'fuentes cercanas o ejecute escenarios separados.'
                ).format(self.width_spin.value(),
                         self.domain_height_spin.value()))
        parameters = {
            "SOURCE_MODE": 0,
            "SOURCE": "{:.12g},{:.12g} [EPSG:4326]".format(
                self.wgs84_point.x(), self.wgs84_point.y()),
            "EMISSION": self.emission_spin.value(),
            "EMISSION_UNIT": self.emission_unit_combo.currentIndex(),
            "WIND_MODE": self.wind_mode_combo.currentIndex(),
            "WIND_SPEED": self.wind_speed_spin.value(),
            "WIND_FROM": self.wind_from_spin.value(),
            "EFFECTIVE_HEIGHT": self._active_height_spin().value(),
            "HEIGHT_MODE": self.height_mode_combo.currentIndex(),
            "STACK_DIAMETER": self.stack_diameter_spin.value(),
            "EXIT_VELOCITY": self.exit_velocity_spin.value(),
            "STACK_TEMPERATURE_C": self.stack_temperature_spin.value(),
            "AMBIENT_TEMPERATURE_C": self.ambient_temperature_spin.value(),
            "AMBIENT_GRADIENT_C_KM": self.ambient_gradient_spin.value(),
            "STACK_TIP_DOWNWASH":
                self.stack_tip_downwash_combo.currentIndex(),
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
        if self.sources:
            parameters.update({
                "SOURCE_MODE": 1,
                "SOURCES": self._build_source_layer(),
                "SOURCE_NAME_FIELD": "name",
                "SOURCE_EMISSION_FIELD": "emission",
                "SOURCE_HEIGHT_FIELD": "height_m",
                "SOURCE_DIAMETER_FIELD": "diameter_m",
                "SOURCE_EXIT_VELOCITY_FIELD": "exit_m_s",
                "SOURCE_TEMPERATURE_FIELD": "temp_c",
            })
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

    def _parameter_widgets(self, height_mode=None):
        return {
            "EMISSION": self.emission_spin,
            "EMISSION_UNIT": self.emission_unit_combo,
            "WIND_MODE": self.wind_mode_combo,
            "WIND_SPEED": self.wind_speed_spin,
            "WIND_FROM": self.wind_from_spin,
            "EFFECTIVE_HEIGHT": self._active_height_spin(height_mode),
            "HEIGHT_MODE": self.height_mode_combo,
            "STACK_DIAMETER": self.stack_diameter_spin,
            "EXIT_VELOCITY": self.exit_velocity_spin,
            "STACK_TEMPERATURE_C": self.stack_temperature_spin,
            "AMBIENT_TEMPERATURE_C": self.ambient_temperature_spin,
            "AMBIENT_GRADIENT_C_KM": self.ambient_gradient_spin,
            "STACK_TIP_DOWNWASH": self.stack_tip_downwash_combo,
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
        for key in ("SOURCES", "SOURCE_NAME_FIELD", "SOURCE_EMISSION_FIELD",
                    "SOURCE_HEIGHT_FIELD", "SOURCE_DIAMETER_FIELD",
                    "SOURCE_EXIT_VELOCITY_FIELD",
                    "SOURCE_TEMPERATURE_FIELD"):
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
            "schema_version": 4,
            "plugin_version": "0.16.5",
            "algorithm": self.ALGORITHM_ID,
            "name": self.scenario_edit.text().strip(),
            "source_input": {
                "x": self.source_point.x(), "y": self.source_point.y(),
                "crs": self.source_crs.toWkt()},
            "sources": self.sources,
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
        if (document.get("schema_version") not in (1, 2, 3, 4) or
                document.get("algorithm") != self.ALGORITHM_ID):
            raise ValueError(tr('Formato de escenario incompatible'))
        self._safe_name(document["name"])
        parameters = dict(document["parameters"])
        parameters.pop("SOURCE_MODE", None)
        # Extra parameters from earlier schemas are ignored. All scenarios use
        # the Masters 2008 / Martin 1976 formulation.
        parameters.setdefault("WIND_REFERENCE_HEIGHT", 10.0)
        parameters.setdefault("WIND_EXPOSURE", 0)
        parameters.setdefault("HEIGHT_MODE", 0)
        parameters.setdefault("STACK_DIAMETER", 2.0)
        parameters.setdefault("EXIT_VELOCITY", 10.0)
        parameters.setdefault("STACK_TEMPERATURE_C", 126.85)
        parameters.setdefault("AMBIENT_TEMPERATURE_C", 26.85)
        parameters.setdefault("AMBIENT_GRADIENT_C_KM", 2.0)
        parameters.setdefault("STACK_TIP_DOWNWASH", 0)
        widgets = self._parameter_widgets(parameters["HEIGHT_MODE"])
        for key, widget in widgets.items():
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
        loaded_sources = document.get("sources", [])
        if not isinstance(loaded_sources, list):
            raise ValueError(tr('Tabla de fuentes inválida'))
        required_source_keys = {
            'name', 'longitude', 'latitude', 'emission_kg_s', 'height_m',
            'diameter_m', 'exit_velocity_m_s', 'temperature_c'}
        for row in loaded_sources:
            if (not isinstance(row, dict) or
                    not required_source_keys <= set(row)):
                raise ValueError(tr('Tabla de fuentes inválida'))
            numeric = [row[key] for key in required_source_keys - {'name'}]
            if (any(isinstance(value, bool) or
                    not isinstance(value, (int, float)) or
                    not math.isfinite(value) for value in numeric) or
                    not -180 <= row['longitude'] <= 180 or
                    not -90 <= row['latitude'] <= 90 or
                    row['emission_kg_s'] < 0 or
                    min(row['height_m'], row['diameter_m'],
                        row['exit_velocity_m_s']) <= 0 or
                    row['temperature_c'] <= -273.15):
                raise ValueError(tr('Tabla de fuentes inválida'))
        self.sources = loaded_sources
        self._invalidate_source_layer()
        self._update_source_count()
        self.height_mode_combo.setCurrentIndex(parameters["HEIGHT_MODE"])
        for key, widget in widgets.items():
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(parameters[key])
            else:
                widget.setValue(parameters[key])
        self.csv_edit.setText(str(csv_path))
        wind_import = document.get("wind_import") or {}
        self.wind_original_path = wind_import.get("source_file")
        self.wind_import_summary = wind_import.get("summary")
        self._sync_wind_controls()
        self._sync_height_controls()
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
