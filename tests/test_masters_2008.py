import math
import unittest

import numpy as np

from gaussian_core import (
    gaussian_concentration,
    masters_2008_dispersion_sigmas,
    masters_2008_minimum_positive_x_m,
    masters_2008_wind_speed_at_height,
)


class Masters2008Tests(unittest.TestCase):
    DISTANCES_KM = np.array([.2, .4, .6, .8, 1., 2., 4., 8., 16., 20.])
    TABLE_7_9_SIGMA_Y = {
        "A": [51, 94, 135, 174, 213, 396, 736, 1367, 2540, 3101],
        "B": [37, 69, 99, 128, 156, 290, 539, 1001, 1860, 2271],
        "C": [25, 46, 66, 85, 104, 193, 359, 667, 1240, 1514],
        "D": [16, 30, 43, 56, 68, 126, 235, 436, 811, 990],
        "E": [12, 22, 32, 41, 50, 94, 174, 324, 602, 735],
        "F": [8, 15, 22, 28, 34, 63, 117, 218, 405, 495],
    }
    TABLE_7_9_SIGMA_Z = {
        "A": [29, 84, 173, 295, 450, 1953],  # Later entries are blank.
        "B": [20, 40, 63, 86, 110, 234, 498, 1063, 2274, 2904],
        "C": [14, 26, 38, 50, 61, 115, 216, 406, 763, 934],
        "D": [9, 15, 21, 27, 31, 51, 78, 117, 173, 196],
        "E": [6, 11, 15, 18, 22, 34, 51, 70, 95, 104],
        "F": [4, 7, 9, 12, 14, 22, 32, 42, 55, 59],
    }

    def test_table_7_9_rounded_values(self):
        for stability in "ABCDEF":
            with self.subTest(stability=stability):
                sy, sz = masters_2008_dispersion_sigmas(
                    self.DISTANCES_KM * 1000., stability)
                np.testing.assert_allclose(
                    sy, self.TABLE_7_9_SIGMA_Y[stability],
                    rtol=0, atol=.51)
                expected_z = self.TABLE_7_9_SIGMA_Z[stability]
                np.testing.assert_allclose(
                    sz[:len(expected_z)], expected_z,
                    rtol=0, atol=.51)

    def test_equation_7_46_example_7_11(self):
        speed = masters_2008_wind_speed_at_height(
            2.5, reference_height_m=10., target_height_m=300.,
            stability="C", exposure="rough")
        self.assertEqual(round(float(speed), 1), 4.9)
        self.assertAlmostEqual(
            float(speed), 2.5 * (300. / 10.) ** .2, places=14)

    def test_flat_exposure_uses_point_six_multiplier(self):
        rough = masters_2008_wind_speed_at_height(
            5., 10., 50., "D", "rough")
        flat = masters_2008_wind_speed_at_height(
            5., 10., 50., "D", "flat")
        self.assertAlmostEqual(float(rough), 5. * 5. ** .25)
        self.assertAlmostEqual(float(flat), 5. * 5. ** .15)
        self.assertLess(flat, rough)

    def test_masters_concentration_uses_published_sigmas(self):
        result = gaussian_concentration(
            1000., 0., 0., emission_kg_s=.04, wind_speed_m_s=5.,
            effective_height_m=50., stability="D")
        sy, sz = 68., 33.2 - 1.7
        expected = (.04 / (math.pi * 5. * sy * sz) *
                    math.exp(-(50. ** 2) / (2. * sz ** 2)))
        np.testing.assert_allclose(result, expected, rtol=1e-14, atol=0)

    def test_no_artificial_vertical_cap_is_applied(self):
        _, sz = masters_2008_dispersion_sigmas(4000., "A")
        self.assertGreater(float(sz), 8000.)

    def test_only_mathematical_sigma_z_roots_limit_short_distance(self):
        expected = {"A": 0., "B": 0., "C": 0.,
                    "D": 16.5859017, "E": 14.6286512,
                    "F": 6.6154952}
        for stability, distance in expected.items():
            with self.subTest(stability=stability):
                self.assertAlmostEqual(
                    masters_2008_minimum_positive_x_m(stability),
                    distance, places=6)
        # Between 20 and 100 m the published equations are evaluated directly.
        for stability in "ABCDEF":
            sy, sz = masters_2008_dispersion_sigmas(
                np.array([20., 50., 100.]), stability)
            self.assertTrue(np.all(sy > 0))
            self.assertTrue(np.all(sz > 0))

    def test_invalid_or_nonphysical_inputs(self):
        for arguments in [
                (5., 0., 50., "D", "rough"),
                (0., 10., 50., "D", "rough"),
                (5., 10., 50., "D", "urban"),
                (5., 10., 50., "G", "rough")]:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                masters_2008_wind_speed_at_height(*arguments)
        with self.assertRaises(ValueError):
            masters_2008_dispersion_sigmas(1., "D")
        sy, sz = masters_2008_dispersion_sigmas(20., "D")
        self.assertGreater(float(sy), 0.)
        self.assertGreater(float(sz), 0.)
        self.assertEqual(float(gaussian_concentration(
            -1., 0., 0., emission_kg_s=.04, wind_speed_m_s=5.,
            effective_height_m=50., stability="D")), 0.)


if __name__ == "__main__":
    unittest.main()
