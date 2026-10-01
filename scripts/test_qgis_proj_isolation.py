"""Verify that the plugin ignores a foreign PROJ data override safely."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import sys
import tempfile

from check_qgis_runtime import configure_application, configure_macos_qgis_bundle


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qgis_plugin"))


def main():
    contents = configure_macos_qgis_bundle()
    from qgis.core import Qgis, QgsApplication

    app = QgsApplication([], False)
    configure_application(app, contents)
    app.initQgis()
    old_lib = os.environ.get("PROJ_LIB")
    old_data = os.environ.get("PROJ_DATA")
    try:
        with tempfile.TemporaryDirectory(prefix="foreign-proj-") as foreign:
            os.environ["PROJ_LIB"] = foreign
            os.environ.pop("PROJ_DATA", None)
            import gaussian_educativo
            import pyproj
            from gaussian_educativo.gaussian_spatial import (
                locate_source_coordinates)

            def create_crs(index):
                code = 4326 + index % 2
                crs_ok = all(pyproj.CRS.from_epsg(code).to_epsg() == code
                             for _ in range(250))
                located = locate_source_coordinates(
                    -70.193195 + index * 1e-6, -20.805320,
                    input_crs="EPSG:4326")
                return crs_ok and located.crs.to_epsg() == 32719

            thread_stress = all(ThreadPoolExecutor(max_workers=8).map(
                create_crs, range(16)))
            configured = Path(gaussian_educativo.QGIS_PROJ_DATA_PATH)
            report = {
                "status": "passed" if all((
                    (configured / "proj.db").is_file(),
                    Path(pyproj.datadir.get_data_dir()) == configured,
                    os.environ.get("PROJ_LIB") == foreign,
                    "PROJ_DATA" not in os.environ,
                    thread_stress,
                )) else "failed",
                "qgis": Qgis.QGIS_VERSION,
                "pyproj": pyproj.__version__,
                "proj": pyproj.proj_version_str,
                "qgis_proj_data": str(configured),
                "environment_restored": (
                    os.environ.get("PROJ_LIB") == foreign and
                    "PROJ_DATA" not in os.environ),
                "thread_stress": thread_stress,
            }
    finally:
        if old_lib is None:
            os.environ.pop("PROJ_LIB", None)
        else:
            os.environ["PROJ_LIB"] = old_lib
        if old_data is None:
            os.environ.pop("PROJ_DATA", None)
        else:
            os.environ["PROJ_DATA"] = old_data
        app.exitQgis()
    output = ROOT / "validation/qgis_proj_isolation.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
