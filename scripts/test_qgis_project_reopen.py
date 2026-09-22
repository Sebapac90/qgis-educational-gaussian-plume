"""Reopen saved MVP projects and verify paths, CRS and persisted styles."""
from pathlib import Path
import argparse
import os
import json

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="*")
    parser.add_argument("--expected-layers", type=int, default=3)
    parser.add_argument("--report", default="qgis_project_reopen.json")
    args = parser.parse_args()
    contents = configure_macos_qgis_bundle()
    from qgis.PyQt.QtCore import QSize
    from qgis.core import (QgsApplication, QgsMapRendererParallelJob,
                           QgsMapSettings, QgsProject, QgsRasterLayer)
    app = QgsApplication([], False)
    prefix = contents / "MacOS" if contents else Path(os.environ["QGIS_PREFIX_PATH"])
    configure_application(app, contents)
    app.initQgis()
    reports = []
    try:
        project = QgsProject.instance()
        paths = [ROOT / "outputs/qgis_plugin" / ("proyecto_mvp_040_" + name + ".qgz")
                 for name in ("fijo", "extendido", "viento_csv")]
        paths.append(ROOT / "outputs/qgis_scenarios/proyecto_patache_080.qgz")
        if args.projects:
            paths = [Path(path) for path in args.projects]
        for path in paths:
            project.clear()
            opened = project.read(str(path))
            layers = list(project.mapLayers().values())
            raster = next((layer for layer in layers
                           if isinstance(layer, QgsRasterLayer)), None)
            details = []
            for layer in layers:
                item = {"name": layer.name(), "valid": layer.isValid(),
                        "crs": layer.crs().authid(),
                        "renderer": type(layer.renderer()).__name__}
                if not isinstance(layer, QgsRasterLayer):
                    item["labels"] = layer.labelsEnabled()
                    if layer.renderer().type() == "singleSymbol":
                        symbol_layer = layer.renderer().symbol().symbolLayer(0)
                        if hasattr(symbol_layer, "path"):
                            item["svg_exists"] = Path(symbol_layer.path()).is_file()
                details.append(item)
            valid = (opened and len(layers) == args.expected_layers and raster is not None and
                     all(item["valid"] and item["crs"] == "EPSG:32719"
                         and item.get("svg_exists", True) for item in details) and
                     any(item.get("labels") for item in details) and
                     all(layer.renderer().type() == "singlebandpseudocolor"
                         for layer in layers if isinstance(layer, QgsRasterLayer)))
            preview = ROOT / "validation" / (path.stem + "_reabierto.png")
            if valid:
                settings = QgsMapSettings()
                ordered = [node.layer() for node in
                           project.layerTreeRoot().findLayers()]
                settings.setLayers(ordered)
                settings.setDestinationCrs(project.crs())
                settings.setExtent(raster.extent())
                settings.setOutputSize(QSize(700, 700))
                job = QgsMapRendererParallelJob(settings)
                job.start()
                job.waitForFinished()
                valid = job.renderedImage().save(str(preview), "PNG")
            reports.append({"project": str(path), "passed": valid,
                            "layers": details, "preview": str(preview)})
        project.clear()
    finally:
        app.exitQgis()
    report = {"status": "passed" if reports and len(reports) == len(paths) and
              all(item["passed"] for item in reports) else "failed",
              "projects": reports}
    (ROOT / "validation" / args.report).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
