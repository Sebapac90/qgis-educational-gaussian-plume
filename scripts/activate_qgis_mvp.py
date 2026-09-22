"""QGIS --code helper used only to open the isolated MVP test profile."""
from qgis.PyQt.QtCore import QTimer
import qgis.utils


def activate():
    name = "gaussian_educativo"
    loaded = qgis.utils.loadPlugin(name)
    started = loaded and qgis.utils.startPlugin(name)
    qgis.utils.iface.showProcessingToolbox()
    if started:
        qgis.utils.plugins[name].show_dock()
        qgis.utils.iface.messageBar().pushSuccess(
            "Pluma Gaussiana Educativa",
            "Proveedor experimental 0.8.1 y panel cargados")
    else:
        qgis.utils.iface.messageBar().pushCritical(
            "Pluma Gaussiana Educativa",
            "No se pudo cargar el proveedor experimental")


QTimer.singleShot(1000, activate)
