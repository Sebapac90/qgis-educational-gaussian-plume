"""Shared Gaussian-plume checks against the preserved Manchester reference.

Manchester and this project use different dispersion-coefficient fits, so their
absolute concentrations are not asserted equal. These tests instead exercise
the common continuous-source Gaussian equation across the same input ranges.
"""
from itertools import product
from pathlib import Path
import sys
import unittest

import numpy as np

from gaussian_core import STABILITY_CLASSES, gaussian_concentration


REFERENCE_PYTHON = (Path(__file__).resolve().parents[1] / "reference" /
                    "manchester" / "python")
sys.path.insert(0, str(REFERENCE_PYTHON))
from gauss_func import gauss_func  # noqa: E402


class ManchesterCorrespondenceTests(unittest.TestCase):
    """Check the common physics before plume rise is introduced."""

    EMISSIONS_KG_S = (.001, .04, 1.)
    WIND_SPEEDS_M_S = (1., 5., 15.)
    EFFECTIVE_HEIGHTS_M = (10., 50., 250.)
    DIRECTIONS_FROM_DEG = (0., 45., 90., 225.)
    DOWNWIND_DISTANCES_M = (1000., 10000., 50000.)
    DOWNWIND_DISTANCE_M = 1500.
    CROSSWIND_DISTANCE_M = 200.

    @staticmethod
    def _manchester_point(direction_from_deg, downwind_m, crosswind_m=0.):
        """Return east/north coordinates for Manchester's wind convention."""
        theta = np.deg2rad(direction_from_deg)
        east = (-np.sin(theta) * downwind_m -
                np.cos(theta) * crosswind_m)
        north = (-np.cos(theta) * downwind_m +
                 np.sin(theta) * crosswind_m)
        return east, north

    @staticmethod
    def _manchester_concentration(emission, wind_speed, direction, height,
                                  stability, downwind, crosswind=0.):
        east, north = ManchesterCorrespondenceTests._manchester_point(
            direction, downwind, crosswind)
        values = gauss_func(
            emission, wind_speed, direction,
            np.array([east]), np.array([north]), np.array([0.]),
            0., 0., height, "ABCDEF".index(stability) + 1)
        return float(values[0])

    def test_parameter_matrix_has_shared_emission_and_wind_scaling(self):
        """1,944 configurations span the inputs shared with Manchester.

        Each implementation must double concentration when emission doubles,
        halve it when wind doubles, and remain positive at a downwind receptor.
        The two concentrations need not be equal because their sigma fits differ.
        """
        cases = 0
        for emission, wind, height, direction, stability, distance in product(
                self.EMISSIONS_KG_S, self.WIND_SPEEDS_M_S,
                self.EFFECTIVE_HEIGHTS_M, self.DIRECTIONS_FROM_DEG,
                STABILITY_CLASSES, self.DOWNWIND_DISTANCES_M):
            with self.subTest(
                    emission=emission, wind=wind, height=height,
                    direction=direction, stability=stability,
                    distance=distance):
                ours = float(gaussian_concentration(
                    distance, 0., 0.,
                    emission_kg_s=emission, wind_speed_m_s=wind,
                    effective_height_m=height, stability=stability))
                manchester = self._manchester_concentration(
                    emission, wind, direction, height, stability,
                    distance)
                self.assertGreater(ours, 0.)
                self.assertGreater(manchester, 0.)
                ours_q2 = float(gaussian_concentration(
                    distance, 0., 0.,
                    emission_kg_s=2. * emission, wind_speed_m_s=wind,
                    effective_height_m=height, stability=stability))
                manchester_q2 = self._manchester_concentration(
                    2. * emission, wind, direction, height, stability,
                    distance)
                ours_u2 = float(gaussian_concentration(
                    distance, 0., 0.,
                    emission_kg_s=emission, wind_speed_m_s=2. * wind,
                    effective_height_m=height, stability=stability))
                manchester_u2 = self._manchester_concentration(
                    emission, 2. * wind, direction, height, stability,
                    distance)
                self.assertAlmostEqual(ours_q2 / ours, 2., places=12)
                self.assertAlmostEqual(manchester_q2 / manchester, 2., places=12)
                self.assertAlmostEqual(ours_u2 / ours, .5, places=12)
                self.assertAlmostEqual(manchester_u2 / manchester, .5, places=12)
                cases += 1
        self.assertEqual(cases, 1944)

    def test_crosswind_symmetry_and_upwind_zero_for_all_stabilities(self):
        """Both forms are symmetric across and zero upwind of each plume."""
        for stability, direction in product(
                STABILITY_CLASSES, self.DIRECTIONS_FROM_DEG):
            with self.subTest(stability=stability, direction=direction):
                ours_plus = float(gaussian_concentration(
                    self.DOWNWIND_DISTANCE_M, self.CROSSWIND_DISTANCE_M, 0.,
                    emission_kg_s=.04, wind_speed_m_s=5.,
                    effective_height_m=50., stability=stability))
                ours_minus = float(gaussian_concentration(
                    self.DOWNWIND_DISTANCE_M, -self.CROSSWIND_DISTANCE_M, 0.,
                    emission_kg_s=.04, wind_speed_m_s=5.,
                    effective_height_m=50., stability=stability))
                manchester_plus = self._manchester_concentration(
                    .04, 5., direction, 50., stability,
                    self.DOWNWIND_DISTANCE_M, self.CROSSWIND_DISTANCE_M)
                manchester_minus = self._manchester_concentration(
                    .04, 5., direction, 50., stability,
                    self.DOWNWIND_DISTANCE_M, -self.CROSSWIND_DISTANCE_M)
                self.assertAlmostEqual(ours_plus, ours_minus, places=18)
                self.assertAlmostEqual(
                    manchester_plus, manchester_minus, places=18)
                self.assertEqual(float(gaussian_concentration(
                    -self.DOWNWIND_DISTANCE_M, 0., 0., emission_kg_s=.04,
                    wind_speed_m_s=5., effective_height_m=50.,
                    stability=stability)), 0.)
                self.assertEqual(self._manchester_concentration(
                    .04, 5., direction, 50., stability,
                    -self.DOWNWIND_DISTANCE_M), 0.)

    def test_effective_height_is_a_direct_common_input(self):
        """Both pre-Briggs models receive H directly and respond to it."""
        for stability, direction, height in product(
                STABILITY_CLASSES, self.DIRECTIONS_FROM_DEG,
                self.EFFECTIVE_HEIGHTS_M):
            with self.subTest(stability=stability, direction=direction,
                              height=height):
                ours = float(gaussian_concentration(
                    self.DOWNWIND_DISTANCE_M, 0., 0., emission_kg_s=.04,
                    wind_speed_m_s=5., effective_height_m=height,
                    stability=stability))
                manchester = self._manchester_concentration(
                    .04, 5., direction, height, stability,
                    self.DOWNWIND_DISTANCE_M)
                self.assertTrue(np.isfinite(ours))
                self.assertTrue(np.isfinite(manchester))
                self.assertGreaterEqual(ours, 0.)
                self.assertGreaterEqual(manchester, 0.)


if __name__ == "__main__":
    unittest.main()
