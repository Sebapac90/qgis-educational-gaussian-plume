# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Processing vertical slice: source, constant wind and styled QGIS outputs."""
from .i18n import tr
from . import i18n
import math
import re

import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsGeometry,
    QgsPointXY, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingOutputNumber, QgsProcessingOutputString,
    QgsProcessingParameterEnum, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile, QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint, QgsProcessingParameterRasterDestination,
    QgsProcessingParameterString, QgsProject, QgsWkbTypes)
from qgis.PyQt.QtCore import QMetaType

from .gaussian_contours import contour_levels
from .gaussian_core import (MASTERS_2008_FIGURE_START_M,
                            masters_2008_minimum_positive_x_m,
                            masters_2008_wind_speed_at_height)
from .gaussian_spatial import (locate_source_coordinates, make_grid,
                               make_grid_bounds)
from .gaussian_units import concentration_factor_from_kg_m3, emission_to_kg_s
from .gaussian_wind import (aggregate_wind_for_calculation,
                            mean_ground_concentration, save_wind_rose,
                            wind_from_config)
from .styles import register_postprocessor


class SimulateGaussianPlumeAlgorithm(QgsProcessingAlgorithm):
    BORDER_THRESHOLD_KG_M3 = 1e-10  # 0.1 µg/m³, independent of display unit
    SOURCE = "SOURCE"
    EMISSION = "EMISSION"
    EMISSION_UNIT = "EMISSION_UNIT"
    WIND_SPEED = "WIND_SPEED"
    WIND_FROM = "WIND_FROM"
    WIND_MODE = "WIND_MODE"
    WIND_FILE = "WIND_FILE"
    WIND_ROSE = "WIND_ROSE"
    EFFECTIVE_HEIGHT = "EFFECTIVE_HEIGHT"
    STABILITY = "STABILITY"
    WIND_REFERENCE_HEIGHT = "WIND_REFERENCE_HEIGHT"
    WIND_EXPOSURE = "WIND_EXPOSURE"
    WIDTH = "WIDTH"
    HEIGHT = "HEIGHT"
    RESOLUTION = "RESOLUTION"
    DOMAIN_POLICY = "DOMAIN_POLICY"
    CONCENTRATION_UNIT = "CONCENTRATION_UNIT"
    CONTOUR_MODE = "CONTOUR_MODE"
    CONTOUR_MINIMUM = "CONTOUR_MINIMUM"
    CONTOUR_LEVELS = "CONTOUR_LEVELS"
    OUTPUT = "OUTPUT"
    ISOLINES = "ISOLINES"
    SOURCE_OUTPUT = "SOURCE_OUTPUT"
    MAXIMUM = "MAXIMUM"
    BORDER_MAXIMUM = "BORDER_MAXIMUM"
    BORDER_NORTH = "BORDER_NORTH"
    BORDER_SOUTH = "BORDER_SOUTH"
    BORDER_WEST = "BORDER_WEST"
    BORDER_EAST = "BORDER_EAST"
    ACTUAL_WIDTH = "ACTUAL_WIDTH"
    ACTUAL_HEIGHT = "ACTUAL_HEIGHT"
    DOMAIN_ITERATIONS = "DOMAIN_ITERATIONS"
    DOMAIN_STATUS = "DOMAIN_STATUS"
    WIND_SAMPLES = "WIND_SAMPLES"
    MEAN_WIND_SPEED = "MEAN_WIND_SPEED"
    REPRESENTATIVE_WIND_FROM = "REPRESENTATIVE_WIND_FROM"
    OUTPUT_CRS = "OUTPUT_CRS"

    EMISSION_UNITS = ("kg/s", "g/s", "mg/s", "µg/s")
    EMISSION_TOKENS = ("kg/s", "g/s", "mg/s", "ug/s")
    CONCENTRATION_UNITS = ("kg/m³", "g/m³", "mg/m³", "µg/m³")
    CONCENTRATION_TOKENS = ("kg/m3", "g/m3", "mg/m3", "ug/m3")
    STABILITY_CLASSES = tuple("ABCDEF")
    WIND_EXPOSURES = ("rough", "flat")

    def name(self):
        return "simular_pluma"

    def displayName(self):
        return tr('Simular pluma gaussiana')

    def group(self):
        return tr('Simulación')

    def groupId(self):
        return "simulacion"

    def createInstance(self):
        return SimulateGaussianPlumeAlgorithm()

    def shortHelpString(self):
        return (tr('Modelo docente estacionario sobre terreno plano basado en Masters y Ela (2008). La dirección es meteorológica DESDE, horaria desde norte verdadero. Predominante y aleatorio uniforme usan 1200 intervalos reproducibles (semilla 22001); predominante usa desviación 40° y aleatorio ignora la dirección ingresada. La tabla de observaciones requiere timestamp_utc (ISO 8601 UTC), direction_from_deg (grados) y wind_speed_m_s (m/s, mayor que cero). Cada fila representa un intervalo de igual duración. La rosa usa 16 sectores; el cálculo agrupa las observaciones en 72 sectores direccionales y siete clases de velocidad antes de promediar las plumas. Las calmas deben excluirse y documentarse por separado. La rapidez se corrige desde la altura de medición hasta la chimenea y la dispersión usa las ecuaciones de Martin. La altura ingresada es la altura física de la chimenea; se supone ascenso de pluma cero y la altura efectiva es igual a ella. No representa terreno, deposición, química, edificios ni ascenso de pluma.'))

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterPoint(
            self.SOURCE, tr('Fuente puntual'),
            defaultValue="-70.193195,-20.805320 [EPSG:4326]"))
        self.addParameter(QgsProcessingParameterNumber(
            self.EMISSION, tr('Emisión'), QgsProcessingParameterNumber.Double,
            defaultValue=40.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.EMISSION_UNIT, tr('Unidad de emisión'), self.EMISSION_UNITS,
            defaultValue=1))
        self.addParameter(QgsProcessingParameterEnum(
            self.WIND_MODE, tr('Entrada de viento'),
            (tr('Constante'), tr('Predominante sintético'),
             tr('Aleatorio uniforme sintético'),
             tr('Tabla CSV de observaciones')),
            defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.WIND_SPEED, tr('Rapidez del viento constante (m/s)'),
            QgsProcessingParameterNumber.Double, defaultValue=5.0,
            minValue=1e-9))
        self.addParameter(QgsProcessingParameterNumber(
            self.WIND_FROM, tr('Dirección constante DESDE (grados)'),
            QgsProcessingParameterNumber.Double, defaultValue=0.0,
            minValue=0.0, maxValue=360.0))
        self.addParameter(QgsProcessingParameterFile(
            self.WIND_FILE, tr('CSV de viento: fecha UTC, grados y m/s'),
            behavior=QgsProcessingParameterFile.File,
            fileFilter="CSV (*.csv)", optional=True))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.WIND_ROSE, tr('Rosa de vientos (PNG opcional)'),
            fileFilter="PNG (*.png)", optional=True,
            createByDefault=False))
        self.addParameter(QgsProcessingParameterNumber(
            self.EFFECTIVE_HEIGHT, tr('Altura de la chimenea (m)'),
            QgsProcessingParameterNumber.Double, defaultValue=50.0,
            minValue=0.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.STABILITY, tr('Estabilidad Pasquill–Gifford'),
            self.STABILITY_CLASSES, defaultValue=3))
        self.addParameter(QgsProcessingParameterNumber(
            self.WIND_REFERENCE_HEIGHT,
            tr('Altura de medición del viento (m)'),
            QgsProcessingParameterNumber.Double, defaultValue=10.0,
            minValue=0.01))
        self.addParameter(QgsProcessingParameterEnum(
            self.WIND_EXPOSURE,
            tr('Exposición del terreno para corregir el viento'),
            (tr('Rugosa'), tr('Plana')), defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.WIDTH, tr('Ancho del dominio (m)'),
            QgsProcessingParameterNumber.Double, defaultValue=10000.0,
            minValue=1.0, maxValue=100000.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.HEIGHT, tr('Alto del dominio (m)'),
            QgsProcessingParameterNumber.Double, defaultValue=10000.0,
            minValue=1.0, maxValue=100000.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.RESOLUTION, tr('Resolución (m)'),
            QgsProcessingParameterNumber.Double, defaultValue=50.0,
            minValue=0.01))
        self.addParameter(QgsProcessingParameterEnum(
            self.DOMAIN_POLICY, tr('Política del dominio'),
            (tr('Fijo: conservar dimensiones'),
             tr('Extender lados que no cumplen el criterio del borde')),
            defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.CONCENTRATION_UNIT, tr('Unidad de concentración'),
            self.CONCENTRATION_UNITS, defaultValue=3))
        self.addParameter(QgsProcessingParameterEnum(
            self.CONTOUR_MODE, tr('Niveles de isolíneas'),
            (tr('Automáticos: serie 1–2–5 + nivel superior'), tr('Manuales')),
            defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.CONTOUR_MINIMUM, tr('Isolínea mínima (unidad de concentración)'),
            QgsProcessingParameterNumber.Double, defaultValue=1.0,
            minValue=1e-30))
        self.addParameter(QgsProcessingParameterString(
            self.CONTOUR_LEVELS,
            tr('Niveles manuales separados por coma (solo modo manual)'),
            defaultValue="1, 2, 5, 10, 20, 50, 100, 200, 300",
            optional=True))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, tr('Concentración')))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.ISOLINES, tr('Isolíneas'), QgsProcessing.TypeVectorLine,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.SOURCE_OUTPUT, tr('Fuente emisora'), QgsProcessing.TypeVectorPoint,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT))
        self.addOutput(QgsProcessingOutputNumber(
            self.MAXIMUM, tr('Concentración máxima')))
        self.addOutput(QgsProcessingOutputNumber(
            self.BORDER_MAXIMUM, tr('Concentración máxima en el borde')))
        self.addOutput(QgsProcessingOutputNumber(
            self.BORDER_NORTH, tr('Máximo del borde norte')))
        self.addOutput(QgsProcessingOutputNumber(
            self.BORDER_SOUTH, tr('Máximo del borde sur')))
        self.addOutput(QgsProcessingOutputNumber(
            self.BORDER_WEST, tr('Máximo del borde oeste')))
        self.addOutput(QgsProcessingOutputNumber(
            self.BORDER_EAST, tr('Máximo del borde este')))
        self.addOutput(QgsProcessingOutputNumber(
            self.ACTUAL_WIDTH, tr('Ancho calculado final (m)')))
        self.addOutput(QgsProcessingOutputNumber(
            self.ACTUAL_HEIGHT, tr('Alto calculado final (m)')))
        self.addOutput(QgsProcessingOutputNumber(
            self.DOMAIN_ITERATIONS, tr('Extensiones realizadas')))
        self.addOutput(QgsProcessingOutputString(
            self.DOMAIN_STATUS, tr('Estado del dominio')))
        self.addOutput(QgsProcessingOutputNumber(
            self.WIND_SAMPLES, tr('Registros o clases de viento')))
        self.addOutput(QgsProcessingOutputNumber(
            self.MEAN_WIND_SPEED, tr('Rapidez media ponderada (m/s)')))
        self.addOutput(QgsProcessingOutputNumber(
            self.REPRESENTATIVE_WIND_FROM,
            tr('Dirección circular representativa DESDE (grados)')))
        self.addOutput(QgsProcessingOutputString(
            self.OUTPUT_CRS, tr('CRS de cálculo')))

    def prepareAlgorithm(self, parameters, context, feedback):
        # Processing prepares on the caller thread before starting its worker.
        # Keep PyProj CRS construction there: the official 3.44 macOS bundle
        # crashes in PROJ when a Qt pooled worker creates a PyProj context.
        point = self.parameterAsPoint(parameters, self.SOURCE, context)
        point_crs = self.parameterAsPointCrs(parameters, self.SOURCE, context)
        if not point_crs.isValid():
            raise QgsProcessingException(tr('La fuente necesita un CRS válido'))
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        if point_crs != wgs84:
            transform = QgsCoordinateTransform(point_crs, wgs84,
                                               context.transformContext())
            point = transform.transform(point)
        try:
            self._source = locate_source_coordinates(point.x(), point.y(),
                                                     input_crs="EPSG:4326")
            self._source_epsg = self._source.crs.to_epsg()
        except (TypeError, ValueError) as error:
            raise QgsProcessingException(str(error)) from None
        return True

    def processAlgorithm(self, parameters, context, feedback):
        source = self._source
        feedback.setProgress(5)
        try:
            width = self.parameterAsDouble(parameters, self.WIDTH, context)
            height = self.parameterAsDouble(parameters, self.HEIGHT, context)
            resolution = self.parameterAsDouble(parameters, self.RESOLUTION, context)
            grid = make_grid(source, width_m=width, height_m=height,
                             resolution_m=resolution)
            emission_index = self.parameterAsEnum(parameters, self.EMISSION_UNIT,
                                                   context)
            emission = self.parameterAsDouble(parameters, self.EMISSION, context)
            emission_kg_s = emission_to_kg_s(
                emission, self.EMISSION_TOKENS[emission_index])
            concentration_index = self.parameterAsEnum(
                parameters, self.CONCENTRATION_UNIT, context)
            concentration_unit = self.CONCENTRATION_TOKENS[concentration_index]
            stability = self.STABILITY_CLASSES[
                self.parameterAsEnum(parameters, self.STABILITY, context)]
            wind_reference_height = self.parameterAsDouble(
                parameters, self.WIND_REFERENCE_HEIGHT, context)
            wind_exposure = self.WIND_EXPOSURES[
                self.parameterAsEnum(parameters, self.WIND_EXPOSURE, context)]
            wind_mode = self.parameterAsEnum(parameters, self.WIND_MODE, context)
            wind_speed = self.parameterAsDouble(parameters, self.WIND_SPEED, context)
            wind_from = self.parameterAsDouble(parameters, self.WIND_FROM, context)
            wind_model = {"wind_mode":
                          ("constant", "prevailing", "fluctuating", "table")[wind_mode],
                          "wind_speed_m_s": wind_speed,
                          "wind_from_deg": wind_from,
                          "wind_hours": 1200,
                          "wind_direction_std_deg": 40.0,
                          "wind_random_seed": 22001}
            if wind_mode == 3:
                wind_file = self.parameterAsFile(
                    parameters, self.WIND_FILE, context)
                if not wind_file:
                    raise ValueError(tr('Seleccione un CSV para el modo tabla'))
                wind_model = {"wind_mode": "table", "wind_file": wind_file}
            wind = wind_from_config(wind_model)
            calculation_wind = aggregate_wind_for_calculation(wind)
            evaluations = int(np.prod(grid.shape)) * calculation_wind.samples
            if evaluations > 50_000_000:
                recommended = 10 * math.ceil(
                    resolution * math.sqrt(evaluations / 50_000_000) / 10)
                raise ValueError(
                    tr('La combinación de grilla y viento requiere {:,} evaluaciones, sobre el límite interactivo de {:,}. Aumente la resolución al menos a {:.0f} m o reduzca el dominio.')
                    .format(evaluations, 50_000_000,
                            recommended))
            effective_height = self.parameterAsDouble(
                parameters, self.EFFECTIVE_HEIGHT, context)
            if effective_height <= 0:
                raise ValueError(
                    tr('El modo Masters requiere una altura de chimenea mayor que cero'))
            concentration = mean_ground_concentration(
                grid, calculation_wind, emission_kg_s=emission_kg_s,
                effective_height_m=effective_height, stability=stability,
                max_evaluations=50_000_000,
                progress_callback=lambda fraction:
                    feedback.setProgress(5 + round(60 * fraction)),
                is_canceled=feedback.isCanceled, direction_sectors=None,
                wind_reference_height_m=wind_reference_height,
                wind_exposure=wind_exposure)
            domain_policy = self.parameterAsEnum(
                parameters, self.DOMAIN_POLICY, context)
            if domain_policy == 1 and wind_mode == 3:
                raise ValueError(
                    tr('La extensión automática aún no admite tablas CSV; use dominio fijo para esta versión'))
            if domain_policy == 1:
                grid, concentration, domain_iterations, domain_status = \
                    self._extend_domain(
                        grid, concentration, feedback, wind=calculation_wind,
                        emission_kg_s=emission_kg_s,
                        effective_height_m=effective_height,
                        stability=stability,
                        wind_reference_height_m=wind_reference_height,
                        wind_exposure=wind_exposure)
            else:
                domain_iterations = 0
                domain_status = "fixed"
        except (IndexError, TypeError, ValueError) as error:
            raise QgsProcessingException(str(error)) from None

        if feedback.isCanceled():
            return {}
        feedback.setProgress(70)
        concentration_factor = concentration_factor_from_kg_m3(
            concentration_unit)
        displayed = concentration * concentration_factor
        border_threshold = self.BORDER_THRESHOLD_KG_M3 * concentration_factor
        maximum = float(np.nanmax(displayed))
        edges = self._edge_maxima(displayed)
        border_maximum = max(edges.values())
        failing_edges = self._failing_edges(
            edges, maximum, border_threshold)
        if domain_policy == 0:
            domain_status = ("fixed_truncated" if failing_edges
                             else "fixed_edge_criteria_met")
        elif failing_edges:
            domain_status = domain_status + "_truncated"
        else:
            domain_status = "extended_edge_criteria_met"
        west, south, east, north = grid.bounds
        actual_width, actual_height = east - west, north - south
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        self._write_geotiff(output_path, grid, displayed, self._source_epsg,
                            concentration_unit, emission, self.EMISSION_TOKENS[emission_index],
                            wind, calculation_wind.samples,
                            effective_height, stability,
                            wind_reference_height,
                            wind_exposure,
                            domain_policy=("fixed" if domain_policy == 0 else
                                           "extend_failing_edges"),
                            domain_status=domain_status,
                            domain_iterations=domain_iterations,
                            edge_maxima=edges)
        minimum = self.parameterAsDouble(parameters, self.CONTOUR_MINIMUM, context)
        contour_mode = self.parameterAsEnum(parameters, self.CONTOUR_MODE, context)
        requested_levels = "auto_125_upper"
        if contour_mode == 1:
            requested_levels = self._manual_levels(
                self.parameterAsString(parameters, self.CONTOUR_LEVELS, context))
        levels = contour_levels(maximum, minimum, requested_levels).tolist()
        calculation_crs = QgsCoordinateReferenceSystem(
            "EPSG:{}".format(self._source_epsg))
        isoline_id = self._write_isolines(
            parameters, context, grid, displayed, levels,
            concentration_unit, calculation_crs)
        source_id = self._write_source(
            parameters, context, source, calculation_crs)
        wind_rose_path = self.parameterAsFileOutput(
            parameters, self.WIND_ROSE, context)
        if wind_rose_path:
            save_wind_rose(wind, wind_rose_path, language=i18n.language())
        feedback.setProgress(95)
        feedback.pushInfo(tr('CRS de cálculo: EPSG:{}').format(self._source_epsg))
        feedback.pushInfo(tr('Máximo: {:.12g} {}').format(maximum, concentration_unit))
        feedback.pushInfo(
            tr('Viento: {} registro(s), {} clase(s) de cálculo, rapidez media {:.6g} m/s').format(
                wind.samples, calculation_wind.samples, wind.mean_speed_m_s))
        feedback.pushInfo(tr('Isolíneas: {}').format(
            ", ".join("{:g}".format(level) for level in levels) or "ninguna"))
        feedback.pushInfo(
            tr('Dominio final: {:g} × {:g} m; estado: {}').format(
                actual_width, actual_height, domain_status))
        if failing_edges:
            border_ratio = (100.0 * border_maximum / maximum
                            if maximum > 0.0 else 0.0)
            feedback.pushWarning(
                tr('Resultado calculado, pero el dominio no contiene la pluma hasta el umbral de {:.12g} {}. Máximo en el borde: {:.12g} {} ({:.3g}% del máximo). Lados que no cumplen: {}. Documente el resultado como truncado.')
                .format(border_threshold, concentration_unit, border_maximum,
                        concentration_unit, border_ratio,
                        ", ".join(failing_edges)))
        elif domain_policy == 1:
            feedback.pushInfo(
                tr('Los bordes del dominio final cumplen los criterios muestreados de 0.1 µg/m³ y 1% del máximo; esto no demuestra contención física.'))
        label = self.CONCENTRATION_UNITS[concentration_index]
        if context.willLoadLayerOnCompletion(output_path):
            register_postprocessor(
                context, output_path, "raster", levels=levels,
                maximum=maximum, transparent_below=border_threshold,
                unit_label=label)
        if context.willLoadLayerOnCompletion(isoline_id):
            register_postprocessor(context, isoline_id, "isolines",
                                   levels=levels, unit_label=label)
        if context.willLoadLayerOnCompletion(source_id):
            register_postprocessor(context, source_id, "source")
        feedback.setProgress(100)
        return {self.OUTPUT: output_path, self.ISOLINES: isoline_id,
                self.SOURCE_OUTPUT: source_id, self.WIND_ROSE: wind_rose_path,
                self.MAXIMUM: maximum,
                self.BORDER_MAXIMUM: border_maximum,
                self.BORDER_NORTH: edges["norte"],
                self.BORDER_SOUTH: edges["sur"],
                self.BORDER_WEST: edges["oeste"],
                self.BORDER_EAST: edges["este"],
                self.ACTUAL_WIDTH: actual_width,
                self.ACTUAL_HEIGHT: actual_height,
                self.DOMAIN_ITERATIONS: domain_iterations,
                self.DOMAIN_STATUS: domain_status,
                self.WIND_SAMPLES: wind.samples,
                self.MEAN_WIND_SPEED: wind.mean_speed_m_s,
                self.REPRESENTATIVE_WIND_FROM:
                    (wind.representative_from_deg
                     if wind.representative_from_deg is not None else -1.0),
                self.OUTPUT_CRS: "EPSG:{}".format(self._source_epsg)}

    @staticmethod
    def _edge_maxima(values):
        return {"norte": float(np.nanmax(values[0, :])),
                "sur": float(np.nanmax(values[-1, :])),
                "oeste": float(np.nanmax(values[:, 0])),
                "este": float(np.nanmax(values[:, -1]))}

    @staticmethod
    def _failing_edges(edges, maximum, absolute_threshold):
        if maximum <= 0.0:
            return []
        return [name for name, value in edges.items()
                if value >= absolute_threshold or value / maximum >= 0.01]

    def _extend_domain(self, grid, concentration, feedback, wind, **model):
        """Double only failing margins while respecting the grid safety caps."""
        iterations = 0
        while iterations < 10:
            maximum = float(np.nanmax(concentration))
            edges = self._edge_maxima(concentration)
            failing = self._failing_edges(
                edges, maximum, self.BORDER_THRESHOLD_KG_M3)
            if not failing:
                return grid, concentration, iterations, "edge_criteria_met"
            west, south, east, north = grid.bounds
            source = grid.source
            candidate = [west, south, east, north]
            if "oeste" in failing:
                candidate[0] = source.easting_m - 2 * (source.easting_m - west)
            if "sur" in failing:
                candidate[1] = source.northing_m - 2 * (source.northing_m - south)
            if "este" in failing:
                candidate[2] = source.easting_m + 2 * (east - source.easting_m)
            if "norte" in failing:
                candidate[3] = source.northing_m + 2 * (north - source.northing_m)
            try:
                candidate_grid = make_grid_bounds(
                    source, west_m=candidate[0], south_m=candidate[1],
                    east_m=candidate[2], north_m=candidate[3],
                    resolution_m=grid.resolution_m)
            except ValueError:
                return grid, concentration, iterations, "safety_limit_reached"
            candidate_evaluations = (int(np.prod(candidate_grid.shape)) *
                                     wind.samples)
            if candidate_evaluations > 50_000_000:
                return (grid, concentration, iterations,
                        "computational_limit_reached")
            grid = candidate_grid
            concentration = mean_ground_concentration(
                grid, wind, max_evaluations=50_000_000,
                is_canceled=feedback.isCanceled, direction_sectors=None,
                **model)
            iterations += 1
            feedback.setProgress(min(65, 10 + iterations * 10))
            if feedback.isCanceled():
                raise QgsProcessingException(tr('Proceso cancelado'))
        return grid, concentration, iterations, "iteration_limit_reached"

    @staticmethod
    def _manual_levels(text):
        try:
            values = [float(value) for value in re.split(r"[,;\s]+", text.strip())
                      if value]
        except ValueError:
            raise QgsProcessingException(
                tr('Los niveles manuales deben ser números separados por coma')) from None
        if not values or any(not math.isfinite(value) or value <= 0
                             for value in values):
            raise QgsProcessingException(
                tr('Ingrese al menos un nivel manual finito y positivo'))
        return values

    def _write_isolines(self, parameters, context, grid, values, levels,
                         unit, crs):
        fields = QgsFields()
        fields.append(QgsField("id", QMetaType.Type.Int))
        fields.append(QgsField("concentration", QMetaType.Type.Double))
        fields.append(QgsField("unit", QMetaType.Type.QString, len=12))
        fields.append(QgsField("label", QMetaType.Type.QString, len=32))
        sink, destination = self.parameterAsSink(
            parameters, self.ISOLINES, context, fields,
            QgsWkbTypes.LineString, crs)
        if sink is None:
            raise QgsProcessingException(tr('No se pudo crear la capa de isolíneas'))
        if not levels:
            return destination

        raster = gdal.GetDriverByName("MEM").Create(
            "", grid.shape[1], grid.shape[0], 1, gdal.GDT_Float64)
        west, south, east, north = grid.bounds
        raster.SetGeoTransform((west, grid.resolution_m, 0.0, north, 0.0,
                                -grid.resolution_m))
        band = raster.GetRasterBand(1)
        band.SetNoDataValue(-9999.0)
        band.WriteArray(np.where(np.isfinite(values), values, -9999.0)
                        .astype(np.float64))

        vectors = ogr.GetDriverByName("Memory").CreateDataSource("")
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(int(crs.authid().split(":")[1]))
        layer = vectors.CreateLayer("isolines", spatial_reference,
                                    ogr.wkbLineString)
        layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
        layer.CreateField(ogr.FieldDefn("elevation", ogr.OFTReal))
        result = gdal.ContourGenerateEx(
            band, layer,
            options=["FIXED_LEVELS={}".format(
                         ",".join("{:.17g}".format(level) for level in levels)),
                     "ID_FIELD=0", "ELEV_FIELD=1"])
        if result != 0:
            raise QgsProcessingException(tr('GDAL no pudo calcular las isolíneas'))
        for item in layer:
            geometry = item.GetGeometryRef()
            if geometry is None or geometry.IsEmpty():
                continue
            level = float(item.GetField("elevation"))
            feature = QgsFeature(fields)
            qgis_geometry = QgsGeometry()
            qgis_geometry.fromWkb(bytes(geometry.ExportToWkb()))
            feature.setGeometry(qgis_geometry)
            feature.setAttributes([int(item.GetField("id")), level, unit,
                                   "{:g}".format(level)])
            if not sink.addFeature(feature, QgsFeatureSink.FastInsert):
                raise QgsProcessingException(tr('No se pudo escribir una isolínea'))
        return destination

    def _write_source(self, parameters, context, source, crs):
        fields = QgsFields()
        fields.append(QgsField("type", QMetaType.Type.QString, len=16))
        fields.append(QgsField("longitude", QMetaType.Type.Double))
        fields.append(QgsField("latitude", QMetaType.Type.Double))
        fields.append(QgsField("easting", QMetaType.Type.Double))
        fields.append(QgsField("northing", QMetaType.Type.Double))
        sink, destination = self.parameterAsSink(
            parameters, self.SOURCE_OUTPUT, context, fields,
            QgsWkbTypes.Point, crs)
        if sink is None:
            raise QgsProcessingException(tr('No se pudo crear la capa de fuente'))
        feature = QgsFeature(fields)
        feature.setGeometry(QgsGeometry.fromPointXY(
            QgsPointXY(source.easting_m, source.northing_m)))
        feature.setAttributes(["source", source.longitude_deg,
                               source.latitude_deg, source.easting_m,
                               source.northing_m])
        if not sink.addFeature(feature, QgsFeatureSink.FastInsert):
            raise QgsProcessingException(tr('No se pudo escribir la fuente'))
        return destination

    @staticmethod
    def _write_geotiff(path, grid, values, epsg, unit, emission,
                       emission_unit, wind, calculation_wind_samples,
                       effective_height, stability,
                       wind_reference_height, wind_exposure, domain_policy,
                       domain_status, domain_iterations, edge_maxima):
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(path, grid.shape[1], grid.shape[0], 1,
                                gdal.GDT_Float64,
                                options=["COMPRESS=DEFLATE"])
        if dataset is None:
            raise QgsProcessingException(tr('No se pudo crear el GeoTIFF'))
        west, south, east, north = grid.bounds
        dataset.SetGeoTransform((west, grid.resolution_m, 0.0, north, 0.0,
                                 -grid.resolution_m))
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(int(epsg))
        dataset.SetProjection(spatial_reference.ExportToWkt())
        wind_factor = float(masters_2008_wind_speed_at_height(
            1.0, wind_reference_height, effective_height, stability,
            wind_exposure))
        minimum_x = masters_2008_minimum_positive_x_m(stability)
        dataset.SetMetadata({"emission_value": str(emission),
                             "emission_unit": emission_unit,
                             "wind_mode": wind.mode,
                             "wind_samples": str(wind.samples),
                             "wind_source_total_rows":
                                 ("" if wind.source_total_rows is None else
                                  str(wind.source_total_rows)),
                             "wind_excluded_calm_rows":
                                 str(wind.excluded_calm_rows),
                             "wind_excluded_variable_rows":
                                 str(wind.excluded_variable_rows),
                             "wind_excluded_missing_rows":
                                 str(wind.excluded_missing_rows),
                             "wind_concentration_basis":
                                 "directional observations with positive speed; conditional weights sum to 1",
                             "wind_calculation_classes":
                                 str(calculation_wind_samples),
                             "wind_mean_speed_m_s": str(wind.mean_speed_m_s),
                             "wind_reference_height_m": str(wind_reference_height),
                             "wind_exposure": wind_exposure,
                             "wind_height_factor": str(wind_factor),
                             "wind_model_mean_speed_m_s":
                                 str(wind.mean_speed_m_s * wind_factor),
                             "wind_representative_from_deg":
                                 ("" if wind.representative_from_deg is None else
                                  str(wind.representative_from_deg)),
                             "wind_source_file": wind.source_file or "",
                             "height_m": str(effective_height),
                             "stack_height_m": str(effective_height),
                             "plume_rise_m": "0",
                             "effective_height_m": str(effective_height),
                             "height_assumption":
                                 "effective height equals stack height; plume rise not calculated",
                             "stability": stability,
                             "dispersion_model": "masters_2008_martin_1976",
                             "near_source_nodata_radius_m":
                                 str(minimum_x),
                             "masters_figure_start_m":
                                 str(MASTERS_2008_FIGURE_START_M),
                             "domain_policy": domain_policy,
                             "domain_status": domain_status,
                             "domain_iterations": str(domain_iterations),
                             "domain_width_m": str(grid.bounds[2] - grid.bounds[0]),
                             "domain_height_m": str(grid.bounds[3] - grid.bounds[1]),
                             "edge_north": str(edge_maxima["norte"]),
                             "edge_south": str(edge_maxima["sur"]),
                             "edge_west": str(edge_maxima["oeste"]),
                             "edge_east": str(edge_maxima["este"]),
                             "edge_concentration_unit": unit,
                             "sampling": "pixel centre, not cell average"})
        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-9999.0)
        band.WriteArray(np.where(np.isfinite(values), values, -9999.0)
                        .astype(np.float64))
        band.SetDescription("Ground concentration ({})".format(unit))
        band.SetMetadata({"units": unit, "receptor_height_m": "0",
                          "terrain": "flat"})
        band.FlushCache()
        dataset.FlushCache()
        dataset = None
