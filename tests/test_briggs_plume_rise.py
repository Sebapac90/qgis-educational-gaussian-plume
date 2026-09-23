import unittest

from gaussian_core import (
    briggs_buoyancy_flux,
    briggs_final_plume_rise,
    briggs_momentum_flux,
    briggs_stability_parameter,
)


class BriggsPlumeRiseTests(unittest.TestCase):
    def test_masters_example_7_14_buoyancy_flux(self):
        flux = briggs_buoyancy_flux(15., 4., 413., 298.)
        radius_form = 9.8 * 2. ** 2 * 15. * (1. - 298. / 413.)
        self.assertAlmostEqual(flux, radius_form, places=12)
        self.assertAlmostEqual(flux, 163.72881355932205, places=12)

    def test_masters_example_7_14_unstable_uses_correct_high_branch(self):
        result = briggs_final_plume_rise(
            stack_height_m=250., stack_diameter_m=4.,
            exit_velocity_m_s=15., stack_temperature_k=413.,
            ambient_temperature_k=298., wind_speed_stack_m_s=5.,
            stability="C")
        self.assertEqual(result.regime, "buoyancy")
        self.assertAlmostEqual(
            result.distance_to_final_rise_m, 914.5280011392415, places=9)
        self.assertAlmostEqual(
            result.plume_rise_m, 164.94085286253545, places=9)
        self.assertAlmostEqual(
            result.effective_height_m, 414.94085286253545, places=9)

    def test_masters_example_7_14_stable(self):
        result = briggs_final_plume_rise(
            stack_height_m=250., stack_diameter_m=4.,
            exit_velocity_m_s=15., stack_temperature_k=413.,
            ambient_temperature_k=298., wind_speed_stack_m_s=5.,
            stability="E", ambient_temperature_gradient_k_m=.002)
        self.assertEqual(result.regime, "buoyancy")
        self.assertAlmostEqual(
            result.stability_parameter_s2,
            0.00039463087248322156, places=15)
        self.assertAlmostEqual(
            result.plume_rise_m, 113.40391093448255, places=9)
        self.assertAlmostEqual(
            result.effective_height_m, 363.40391093448255, places=9)

    def test_exact_flux_threshold_uses_greater_equal_branch(self):
        stack_temperature = 400.
        velocity = 10.
        diameter = 2.
        delta_temperature = (55. * 4. * stack_temperature /
                             (9.8 * velocity * diameter ** 2))
        ambient_temperature = stack_temperature - delta_temperature
        result = briggs_final_plume_rise(
            stack_height_m=100., stack_diameter_m=diameter,
            exit_velocity_m_s=velocity,
            stack_temperature_k=stack_temperature,
            ambient_temperature_k=ambient_temperature,
            wind_speed_stack_m_s=4., stability="D")
        self.assertAlmostEqual(result.buoyancy_flux_m4_s3, 55., places=12)
        self.assertEqual(result.regime, "buoyancy")
        self.assertAlmostEqual(
            result.distance_to_final_rise_m, 119. * 55. ** .4, places=10)
        self.assertAlmostEqual(
            result.plume_rise_m, 38.71 * 55. ** .6 / 4., places=10)

    def test_low_buoyancy_flux_uses_low_branch(self):
        result = briggs_final_plume_rise(
            stack_height_m=50., stack_diameter_m=1.,
            exit_velocity_m_s=10., stack_temperature_k=350.,
            ambient_temperature_k=300., wind_speed_stack_m_s=4.,
            stability="B")
        flux = briggs_buoyancy_flux(10., 1., 350., 300.)
        self.assertLess(flux, 55.)
        self.assertEqual(result.regime, "buoyancy")
        self.assertAlmostEqual(
            result.distance_to_final_rise_m, 49. * flux ** (5. / 8.))
        self.assertAlmostEqual(
            result.plume_rise_m, 21.425 * flux ** (3. / 4.) / 4.)

    def test_warm_plume_below_crossover_uses_momentum(self):
        result = briggs_final_plume_rise(
            stack_height_m=50., stack_diameter_m=1.,
            exit_velocity_m_s=10., stack_temperature_k=310.,
            ambient_temperature_k=300., wind_speed_stack_m_s=5.,
            stability="C")
        self.assertGreater(result.crossover_temperature_k, 10.)
        self.assertEqual(result.regime, "momentum")
        self.assertIsNone(result.distance_to_final_rise_m)
        self.assertAlmostEqual(result.plume_rise_m, 6.)

    def test_neutral_temperature_uses_momentum(self):
        result = briggs_final_plume_rise(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=10., stack_temperature_k=300.,
            ambient_temperature_k=300., wind_speed_stack_m_s=5.,
            stability="D")
        self.assertEqual(result.regime, "momentum")
        self.assertEqual(result.buoyancy_flux_m4_s3, 0.)
        self.assertAlmostEqual(result.plume_rise_m, 12.)
        self.assertAlmostEqual(result.effective_height_m, 62.)

    def test_stable_momentum_uses_lower_limit(self):
        result = briggs_final_plume_rise(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=10., stack_temperature_k=300.,
            ambient_temperature_k=300., wind_speed_stack_m_s=5.,
            stability="F", ambient_temperature_gradient_k_m=.002)
        flux = briggs_momentum_flux(10., 2., 300., 300.)
        stability_parameter = briggs_stability_parameter(300., .002)
        stable = 1.5 * (flux / (5. * stability_parameter ** .5)) ** (1/3)
        neutral = 3. * 2. * 10. / 5.
        self.assertEqual(result.regime, "momentum")
        self.assertAlmostEqual(result.plume_rise_m, min(stable, neutral))

    def test_optional_stack_tip_downwash(self):
        result = briggs_final_plume_rise(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=5., stack_temperature_k=300.,
            ambient_temperature_k=300., wind_speed_stack_m_s=5.,
            stability="D", stack_tip_downwash=True)
        self.assertAlmostEqual(result.stack_tip_downwash_m, -2.)
        self.assertAlmostEqual(result.corrected_stack_height_m, 48.)
        self.assertAlmostEqual(result.plume_rise_m, 6.)
        self.assertAlmostEqual(result.effective_height_m, 54.)

    def test_invalid_inputs(self):
        common = dict(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=10., stack_temperature_k=400.,
            ambient_temperature_k=300., wind_speed_stack_m_s=5.,
            stability="D")
        for key, value in [
                ("stack_height_m", -1.), ("stack_diameter_m", 0.),
                ("exit_velocity_m_s", 0.), ("stack_temperature_k", 0.),
                ("ambient_temperature_k", 0.),
                ("wind_speed_stack_m_s", 0.)]:
            arguments = dict(common)
            arguments[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                briggs_final_plume_rise(**arguments)
        with self.assertRaises(ValueError):
            briggs_final_plume_rise(**dict(common, stability="E"))
        with self.assertRaises(ValueError):
            briggs_final_plume_rise(**dict(
                common, stability="E",
                ambient_temperature_gradient_k_m=-.01))
        with self.assertRaises(ValueError):
            briggs_final_plume_rise(**dict(
                common, stack_tip_downwash="yes"))


if __name__ == "__main__":
    unittest.main()
