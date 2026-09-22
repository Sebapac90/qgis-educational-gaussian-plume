"""QGIS entry point for the educational Gaussian plume plugin."""


def classFactory(iface):
    from .plugin import GaussianEducationalPlugin
    return GaussianEducationalPlugin(iface)
