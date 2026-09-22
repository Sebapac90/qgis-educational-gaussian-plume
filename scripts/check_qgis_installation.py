"""Portable dependency preflight; run inside QGIS's own Python environment.

QGIS Python console (replace the path):
    import runpy
    check = runpy.run_path('/path/to/project/scripts/check_qgis_installation.py')
    check['report']()
"""
import importlib
import json
import platform


def report():
    from qgis.core import Qgis
    from qgis.PyQt.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
    dependencies = {}
    for name in ("numpy", "osgeo.gdal", "pyproj", "matplotlib"):
        try:
            module = importlib.import_module(name)
            dependencies[name] = {"available": True,
                                  "version": str(getattr(module, "__version__", "unknown"))}
        except Exception as error:
            dependencies[name] = {"available": False, "error": str(error)}
    calculation_ok = all(dependencies[name]["available"] for name in
                         ("numpy", "osgeo.gdal", "pyproj"))
    result = {"os": platform.system(), "architecture": platform.machine(),
              "qgis": Qgis.QGIS_VERSION, "python": platform.python_version(),
              "qt": QT_VERSION_STR, "pyqt": PYQT_VERSION_STR,
              "calculation_dependencies_available": calculation_ok,
              "wind_rose_dependency_available": dependencies["matplotlib"]["available"],
              "dependencies": dependencies,
              "note": "Dependency availability does not certify plugin compatibility."}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    from check_qgis_runtime import configure_macos_qgis_bundle
    configure_macos_qgis_bundle()
    report()
