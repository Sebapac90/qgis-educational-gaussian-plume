# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Keep optional Python projection bindings on QGIS's own PROJ database."""
from pathlib import Path
import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsApplication


def _qgis_proj_directory():
    """Return QGIS's packaged PROJ directory without trusting shell overrides."""
    roots = []
    if QCoreApplication.instance() is not None:
        for value in (QgsApplication.prefixPath(), QgsApplication.pkgDataPath()):
            if value:
                roots.append(Path(value))
    try:
        import qgis
        roots.extend(list(Path(qgis.__file__).resolve().parents)[:7])
    except (ImportError, OSError):
        pass
    suffixes = (Path("proj"), Path("share/proj"),
                Path("Resources/qgis/proj"))
    seen = set()
    for root in roots:
        for suffix in suffixes:
            candidate = (root / suffix).resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "proj.db").is_file():
                return candidate
    raise RuntimeError(
        "The PROJ database bundled with QGIS could not be located")


def configure_pyproj_for_qgis():
    """Bind pyproj to QGIS's PROJ data without leaving environment changes.

    Desktop launchers can inherit PROJ_LIB or PROJ_DATA from Conda, Homebrew,
    or another GIS installation.  Mixing that database with QGIS's libproj can
    fail in a Processing worker at native-code level.  The override below is
    present only while importing pyproj; its supported data-dir API retains the
    QGIS path afterward, and the process environment is restored immediately.
    """
    qgis_proj = _qgis_proj_directory()
    missing = object()
    old_lib = os.environ.get("PROJ_LIB", missing)
    old_data = os.environ.get("PROJ_DATA", missing)
    # PROJ < 9 primarily reads PROJ_LIB; current releases prefer PROJ_DATA.
    os.environ["PROJ_LIB"] = str(qgis_proj)
    os.environ["PROJ_DATA"] = str(qgis_proj)
    try:
        from pyproj import CRS, datadir
        datadir.set_data_dir(str(qgis_proj))
        # Force database access now, on plugin initialization, rather than for
        # the first time inside a pooled Processing thread.
        if CRS.from_epsg(4326).to_epsg() != 4326:
            raise RuntimeError("QGIS's PROJ database failed its EPSG:4326 check")
    finally:
        if old_data is missing:
            os.environ.pop("PROJ_DATA", None)
        else:
            os.environ["PROJ_DATA"] = old_data
        if old_lib is missing:
            os.environ.pop("PROJ_LIB", None)
        else:
            os.environ["PROJ_LIB"] = old_lib
    return str(qgis_proj)
