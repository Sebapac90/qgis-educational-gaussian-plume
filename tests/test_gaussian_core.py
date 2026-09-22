import math
import unittest

import numpy as np

from gaussian_core import (gaussian_concentration,
                           masters_2008_dispersion_sigmas)


def plume(x=1000., y=0., z=0., **changes):
    parameters = dict(emission_kg_s=.04, wind_speed_m_s=5.,
                      effective_height_m=50., stability="D")
    parameters.update(changes)
    return gaussian_concentration(x, y, z, **parameters)


class PhysicsTests(unittest.TestCase):
    def test_downwind_and_source_plane(self):
        result = plume(x=[-1000., 0., 1000.])
        np.testing.assert_array_equal(result[:2], [0., 0.])
        self.assertGreater(result[2], 0.)

    def test_symmetry_and_centreline_maximum(self):
        for stability in "ABCDEF":
            with self.subTest(stability=stability):
                c = plume(y=[-100., -50., 0., 50., 100.], stability=stability)
                np.testing.assert_array_equal(c, c[::-1])
                self.assertTrue(c[2] > c[3] > c[4])

    def test_emission_and_wind_scaling(self):
        self.assertAlmostEqual(float(plume(emission_kg_s=.08) / plume()), 2.)
        self.assertAlmostEqual(float(plume(wind_speed_m_s=10.) / plume()), .5)
        self.assertEqual(float(plume(emission_kg_s=0.)), 0.)

    def test_higher_stack_reduces_ground_concentration(self):
        self.assertGreater(plume(effective_height_m=20.), plume())
        self.assertGreater(plume(), plume(effective_height_m=100.))

    def test_ground_reflection_and_units_analytic(self):
        # At x=1 km, class D: sigma_y=68 m and sigma_z=33.2-1.7=31.5 m.
        # Ground reflection doubles the direct-source contribution.
        sy, sz = 68., 31.5
        direct = .04 / (2 * math.pi * 5 * sy * sz) * math.exp(-50**2 / (2*sz**2))
        np.testing.assert_allclose(plume(), 2 * direct, rtol=1.e-14, atol=0)
        # kg/m³ -> micrograms/m³ is explicitly 1e9.
        self.assertTrue(300 < float(plume()) * 1.e9 < 400)

    def test_vertical_reflection_zero_ground_gradient(self):
        # One-sided finite difference approaches the no-flux ground condition.
        c0 = float(plume())
        change1 = abs(float(plume(z=.01)) - c0)
        change2 = abs(float(plume(z=.005)) - c0)
        self.assertAlmostEqual(change1 / change2, 4., places=4)

    def test_sigmas_and_classes(self):
        x = np.array([50., 1000., 100000.])
        values = []
        for stability in "ABCDEF":
            sy, sz = masters_2008_dispersion_sigmas(x, stability)
            self.assertTrue(np.all(sy > 0) and np.all(sz > 0))
            self.assertTrue(np.all(np.diff(sy) > 0))
            self.assertTrue(np.all(np.diff(sz) > 0))
            values.append(float(plume(stability=stability)))
        self.assertEqual(len(set(values)), 6)
        self.assertGreater(
            float(masters_2008_dispersion_sigmas(4000., "A")[1]), 8000.)

    def test_broadcast_and_scalar(self):
        c = plume(x=np.array([[500.], [1000.]]), y=[-50., 0., 50.])
        self.assertEqual(c.shape, (2, 3))
        self.assertEqual(plume().shape, ())
        np.testing.assert_allclose(c[1, 1], plume(), rtol=0, atol=0)
        self.assertEqual(plume(x=[]).shape, (0,))

    def test_invalid_inputs(self):
        for changes in [dict(emission_kg_s=-1), dict(wind_speed_m_s=0),
                        dict(wind_speed_m_s=-2), dict(effective_height_m=-1),
                        dict(stability="G"), dict(stability=1.5),
                        dict(emission_kg_s=[.04]), dict(wind_speed_m_s=np.inf)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plume(**changes)
        for coords in [dict(x=np.nan), dict(y=np.inf), dict(z=-1)]:
            with self.subTest(coords=coords), self.assertRaises(ValueError):
                plume(**coords)
        for x in [0., -1., np.nan, 1.e-30]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                masters_2008_dispersion_sigmas(x, "D")


if __name__ == "__main__":
    unittest.main()
