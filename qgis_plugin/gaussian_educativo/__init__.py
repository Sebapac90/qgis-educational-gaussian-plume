# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""QGIS entry point for the educational Gaussian plume plugin."""

from .qgis_runtime import configure_pyproj_for_qgis


QGIS_PROJ_DATA_PATH = configure_pyproj_for_qgis()


def classFactory(iface):
    from .plugin import GaussianEducationalPlugin
    return GaussianEducationalPlugin(iface)
