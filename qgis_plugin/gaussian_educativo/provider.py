"""Processing provider for educational Gaussian plume algorithms."""
from .i18n import tr
from qgis.core import QgsProcessingProvider

from .simulate_algorithm import SimulateGaussianPlumeAlgorithm


class GaussianProvider(QgsProcessingProvider):
    def id(self):
        return "gaussian_educativo"

    def name(self):
        return tr('Pluma Gaussiana Educativa')

    def longName(self):
        return self.name()

    def loadAlgorithms(self):
        self.addAlgorithm(SimulateGaussianPlumeAlgorithm())
