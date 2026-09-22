# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Post-process QGIS outputs with the same visual rules as the notebook."""
from .i18n import tr
from pathlib import Path

from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsCategorizedSymbolRenderer, QgsColorRampShader,
    QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings,
    QgsProcessingLayerPostProcessorInterface, QgsRasterShader,
    QgsRasterTransparency, QgsRendererCategory,
    QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling)


PALETTE = ("#fff7bc", "#fee391", "#fec44f", "#fe9929", "#ec7014",
           "#dc4c02", "#cc2f02", "#a7191c", "#85000f", "#5f0000")
_POST_PROCESSORS = []
_STYLE_OBJECTS = []  # QGIS 3.40/SIP must retain custom SVG wrappers.


def _colors(count):
    if count <= 0:
        return []
    if count == 1:
        return [PALETTE[-1]]
    return [PALETTE[round(index * (len(PALETTE) - 1) / (count - 1))]
            for index in range(count)]


def style_raster(layer, levels, maximum, transparent_below, unit_label):
    """Apply discrete YlOrRd bands whose breaks follow the isolines."""
    bounds = list(levels[1:]) + [maximum] if levels else [maximum]
    colors = _colors(len(bounds))
    items = [QgsColorRampShader.ColorRampItem(
        value, QColor(color), "≤ {:g} {}".format(value, unit_label))
        for value, color in zip(bounds, colors)]
    ramp = QgsColorRampShader()
    ramp.setColorRampType(QgsColorRampShader.Discrete)
    ramp.setColorRampItemList(items)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    renderer.setOpacity(0.62)
    transparency = QgsRasterTransparency()
    low = QgsRasterTransparency.TransparentSingleValuePixel()
    low.min = 0.0
    low.max = transparent_below
    low.includeMinimum = True
    low.includeMaximum = False
    low.percentTransparent = 100.0
    transparency.setTransparentSingleValuePixelList([low])
    renderer.setRasterTransparency(transparency)
    layer.setRenderer(renderer)
    layer.setName(tr('Concentración ({})').format(unit_label))
    layer.triggerRepaint()


def style_isolines(layer, levels, unit_label):
    """Color contours by level and place buffered labels along each line."""
    categories = []
    for level, color in zip(levels, _colors(len(levels))):
        symbol = QgsLineSymbol.createSimple({"color": color, "width": "0.65"})
        categories.append(QgsRendererCategory(
            float(level), symbol, "{:g} {}".format(level, unit_label)))
    layer.setRenderer(QgsCategorizedSymbolRenderer("concentration", categories))
    label = QgsPalLayerSettings()
    label.fieldName = "label"
    label.placement = QgsPalLayerSettings.Curved
    text = QgsTextFormat()
    text.setSize(9)
    text.setColor(QColor("#263746"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(1.0)
    buffer.setColor(QColor("white"))
    text.setBuffer(buffer)
    label.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(label))
    layer.setLabelsEnabled(True)
    layer.setName(tr('Isolíneas ({})').format(unit_label))
    layer.triggerRepaint()


def style_source(layer):
    """Render the source with the plugin's chimney symbol."""
    icon = Path(__file__).resolve().parent / "icons/chimney.svg"
    svg_layer = QgsSvgMarkerSymbolLayer(str(icon), 8.0)
    symbol = QgsMarkerSymbol([svg_layer])
    renderer = QgsSingleSymbolRenderer(symbol)
    layer.setRenderer(renderer)
    _STYLE_OBJECTS.append((svg_layer, symbol, renderer))


class OutputStyler(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, kind, **settings):
        super().__init__()
        self.kind = kind
        self.settings = settings

    def postProcessLayer(self, layer, context, feedback):
        if self.kind == "raster":
            style_raster(layer, **self.settings)
        elif self.kind == "isolines":
            style_isolines(layer, **self.settings)
        else:
            style_source(layer)


def register_postprocessor(context, layer_id, kind, **settings):
    """Keep the processor alive until QGIS loads and styles its output layer."""
    processor = OutputStyler(kind, **settings)
    _POST_PROCESSORS.append(processor)
    context.layerToLoadOnCompletionDetails(layer_id).setPostProcessor(processor)
