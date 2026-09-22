"""Open a moved Gaussian scenario with the installed QGIS plugin."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle


ROOT = Path(__file__).resolve().parents[1]


class FakeInterface:
    def __init__(self, canvas, window):
        self._canvas = canvas
        self._window = window

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._window


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "validation/qgis_scenario_portability_0130.json")
    args = parser.parse_args()
    scenario_path = args.scenario.resolve()
    plugin_parent = Path(os.environ.get(
        "GAUSSIAN_QGIS_PLUGIN_PARENT",
        str(Path.home() /
            "Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins")))
    sys.path.insert(0, str(plugin_parent))

    contents = configure_macos_qgis_bundle()
    from qgis.PyQt.QtWidgets import QMainWindow
    from qgis.core import QgsApplication
    from qgis.gui import QgsMapCanvas

    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
    dock = None
    try:
        from gaussian_educativo.dock import GaussianDock
        from gaussian_educativo.gaussian_wind import wind_from_config

        canvas = QgsMapCanvas()
        window = QMainWindow()
        dock = GaussianDock(FakeInterface(canvas, window), window)
        dock.load_scenario(scenario_path)
        parameters = dock.algorithm_parameters()
        wind_path = Path(parameters["WIND_FILE"]).resolve()
        wind = wind_from_config(
            {"wind_mode": "table", "wind_file": str(wind_path)})
        document = json.loads(scenario_path.read_text(encoding="utf-8"))
        actual_hash = hashlib.sha256(wind_path.read_bytes()).hexdigest()
        report = {
            "status": "passed",
            "scenario": str(scenario_path),
            "wind_file": str(wind_path),
            "wind_file_is_beside_scenario":
                wind_path.parent == scenario_path.parent,
            "wind_hash_matches": actual_hash == document["wind_sha256"],
            "wind_mode": parameters["WIND_MODE"],
            "wind_samples": wind.samples,
            "source_total_rows": wind.source_total_rows,
            "calm_rows": wind.excluded_calm_rows,
            "variable_rows": wind.excluded_variable_rows,
            "missing_rows": wind.excluded_missing_rows,
            "source_wgs84": [dock.wgs84_point.x(), dock.wgs84_point.y()],
            "status_text": dock.status_label.text(),
        }
        checks = [
            report["wind_file_is_beside_scenario"],
            report["wind_hash_matches"],
            report["wind_mode"] == 3,
            report["wind_samples"] == 478,
            report["source_total_rows"] == 507,
            report["calm_rows"] == 7,
            report["variable_rows"] == 22,
            report["missing_rows"] == 0,
            abs(report["source_wgs84"][0] - (-70.2020601255)) < 1e-9,
            abs(report["source_wgs84"][1] - (-20.8091958517)) < 1e-9,
        ]
        if not all(checks):
            report["status"] = "failed"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["status"] == "passed" else 1
    finally:
        if dock is not None:
            dock.close()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
