"""Create a styled QGIS project for the canonical Patache validation case."""
from pathlib import Path
import json
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/qgis_validation"


def configure_bundle():
    executable = Path(sys.executable).resolve()
    contents = next((p for p in executable.parents if p.name == "Contents"), None)
    if contents:
        os.environ["PROJ_LIB"] = str(contents / "Resources/proj")
        os.environ["PROJ_DATA"] = str(contents / "Resources/proj")
        os.environ["GDAL_DATA"] = str(contents / "Resources/gdal")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return contents
    return None


def main():
    contents = configure_bundle()
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor
    from qgis.core import (Qgis, QgsApplication, QgsCategorizedSymbolRenderer,
        QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsMapRendererParallelJob,
        QgsMapSettings, QgsMarkerSymbol, QgsPalLayerSettings, QgsProject,
        QgsRasterLayer, QgsRasterShader, QgsColorRampShader, QgsRasterTransparency,
        QgsReferencedRectangle, QgsRendererCategory, QgsSingleBandPseudoColorRenderer,
        QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer,
        QgsVectorLayerSimpleLabeling)

    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    app = QgsApplication([], False)
    app.setPrefixPath(str(prefix), True)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project_crs = QgsCoordinateReferenceSystem("EPSG:32719")
        project.setCrs(project_crs)
        project.setTitle("Validación docente · Pluma gaussiana · Patache")

        osm = QgsRasterLayer(
            "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmin=0&zmax=19",
            "OpenStreetMap", "wms")
        raster = QgsRasterLayer(str(OUTPUT / "pluma_ug_m3.tif"),
                                "Concentración (µg/m³)")
        isolines = QgsVectorLayer(str(OUTPUT / "isolineas.geojson"),
                                  "Isolíneas (µg/m³)", "ogr")
        source = QgsVectorLayer(str(OUTPUT / "fuente.geojson"), "Fuente", "ogr")
        layers = (osm, raster, isolines, source)
        if not all(layer.isValid() for layer in layers):
            invalid = [layer.name() for layer in layers if not layer.isValid()]
            raise RuntimeError("Invalid QGIS layers: " + ", ".join(invalid))

        report = json.loads((OUTPUT / "caso_y_resultados.json").read_text())
        levels = [float(v) for v in report["contour_levels"]]
        maximum = float(report["maximum_concentration"])
        palette = ["#fff7bc", "#fee391", "#fec44f", "#fe9929", "#ec7014",
                   "#dc4c02", "#cc2f02", "#a7191c", "#85000f", "#5f0000"]
        upper_bounds = levels[1:] + [maximum]
        colors = palette[-len(upper_bounds):]
        ramp_items = [QgsColorRampShader.ColorRampItem(value, QColor(color),
                      "≤ {:g} µg/m³".format(value))
                      for value, color in zip(upper_bounds, colors)]
        ramp = QgsColorRampShader()
        ramp.setColorRampType(QgsColorRampShader.Discrete)
        ramp.setColorRampItemList(ramp_items)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(ramp)
        raster_renderer = QgsSingleBandPseudoColorRenderer(
            raster.dataProvider(), 1, shader)
        raster_renderer.setOpacity(0.62)
        transparency = QgsRasterTransparency()
        transparent_low = QgsRasterTransparency.TransparentSingleValuePixel()
        transparent_low.min = 0.0
        transparent_low.max = 0.1
        transparent_low.includeMinimum = True
        transparent_low.includeMaximum = False
        transparent_low.percentTransparent = 100.0
        transparency.setTransparentSingleValuePixelList([transparent_low])
        raster_renderer.setRasterTransparency(transparency)
        raster.setRenderer(raster_renderer)

        categories = []
        for index, level in enumerate(levels):
            color = palette[min(index, len(palette) - 1)]
            symbol = isolines.renderer().symbol().clone()
            symbol.setColor(QColor(color))
            symbol.setWidth(0.65)
            categories.append(QgsRendererCategory(level, symbol,
                              "{:g} µg/m³".format(level)))
        isolines.setRenderer(QgsCategorizedSymbolRenderer("concentration", categories))
        label = QgsPalLayerSettings()
        label.fieldName = "label"
        label.placement = QgsPalLayerSettings.Line
        text = QgsTextFormat()
        text.setSize(9)
        text.setColor(QColor("#263746"))
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(1.0)
        buffer.setColor(QColor("white"))
        text.setBuffer(buffer)
        label.setFormat(text)
        isolines.setLabeling(QgsVectorLayerSimpleLabeling(label))
        isolines.setLabelsEnabled(True)

        source.setRenderer(type(source.renderer())(
            QgsMarkerSymbol.createSimple({"name": "triangle", "color": "#8c1620",
                                          "outline_color": "white", "size": "5"})))

        for layer in layers:
            project.addMapLayer(layer)
        extent = QgsReferencedRectangle(raster.extent(), project_crs)
        project.viewSettings().setDefaultViewExtent(extent)
        project.viewSettings().setPresetFullExtent(extent)

        project_path = OUTPUT / "proyecto_validacion.qgz"
        if not project.write(str(project_path)):
            raise RuntimeError("QGIS could not write the validation project")

        transform = QgsCoordinateTransform(source.crs(), project_crs,
                                           project.transformContext())
        source_point = transform.transform(next(source.getFeatures()).geometry().asPoint())
        centre = raster.extent().center()

        settings = QgsMapSettings()
        settings.setLayers([source, isolines, raster])
        settings.setDestinationCrs(project_crs)
        settings.setExtent(raster.extent())
        settings.setOutputSize(QSize(900, 900))
        settings.setBackgroundColor(QColor("white"))
        job = QgsMapRendererParallelJob(settings)
        job.start()
        job.waitForFinished()
        preview_path = OUTPUT / "vista_validacion.png"
        if not job.renderedImage().save(str(preview_path)):
            raise RuntimeError("QGIS could not write the validation preview")

        result = {
            "qgis": Qgis.QGIS_VERSION,
            "project": str(project_path),
            "preview": str(preview_path),
            "project_crs": project.crs().authid(),
            "raster_crs": raster.crs().authid(),
            "isoline_crs": isolines.crs().authid(),
            "source_crs": source.crs().authid(),
            "source_to_raster_centre_m": [source_point.x() - centre.x(),
                                           source_point.y() - centre.y()],
            "maximum_ug_m3": maximum,
            "layers_valid": True,
        }
        (ROOT / "validation/qgis_project.json").write_text(
            json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        app.exitQgis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
