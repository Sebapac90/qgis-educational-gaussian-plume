"""Register Processing and expose the small interactive QGIS dock."""
from .i18n import tr
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .dock import GaussianDock
from .provider import GaussianProvider


class GaussianEducationalPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action = None
        self.dock = None

    def initGui(self):
        self.provider = GaussianProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)
        icon = Path(__file__).resolve().parent / "icons/chimney.svg"
        self.action = QAction(QIcon(str(icon)), tr('Pluma Gaussiana Educativa'),
                              self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.menu_name = tr('&Pluma Gaussiana Educativa')
        self.iface.addPluginToMenu(self.menu_name, self.action)
        self.iface.addToolBarIcon(self.action)
        self.dock = GaussianDock(self.iface, self.iface.mainWindow())
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()

    def show_dock(self):
        self.dock.show()
        self.dock.raise_()

    def unload(self):
        if self.dock is not None:
            self.dock.cleanup()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action is not None:
            self.iface.removePluginMenu(self.menu_name,
                                        self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
