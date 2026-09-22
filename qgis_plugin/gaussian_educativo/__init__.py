# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""QGIS entry point for the educational Gaussian plume plugin."""


def classFactory(iface):
    from .plugin import GaussianEducationalPlugin
    return GaussianEducationalPlugin(iface)
