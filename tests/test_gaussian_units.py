import unittest

from gaussian_units import (concentration_factor_between, display_from_config,
                            emission_from_config, emission_to_kg_s, unit_label)


class UnitTests(unittest.TestCase):
    def test_equivalent_emission_rate_units(self):
        expected = .04
        for value, unit in [(0.04,"kg/s"),(40,"g/s"),(40000,"mg/s"),(4e7,"µg/s")]:
            self.assertEqual(emission_to_kg_s(value,unit),expected)

    def test_concentration_display_conversion(self):
        self.assertEqual(concentration_factor_between("ug/m3","mg/m3"),1e-3)
        self.assertEqual(concentration_factor_between("mg/m³","µg/m³"),1e3)
        self.assertEqual(unit_label("ug/m3"),"µg/m³")

    def test_new_and_legacy_scenario_inputs(self):
        self.assertEqual(emission_from_config({"emission_value":40000,"emission_unit":"mg/s"})[2],.04)
        self.assertEqual(emission_from_config({"emission_g_s":40})[2],.04)
        display={"display":{"concentration_unit":"mg/m3","raster_minimum":.001,
                            "contour_minimum":.01,"contour_levels":[.01,.1,1]}}
        self.assertEqual(display_from_config(display),("mg/m3",.001,.01,[.01,.1,1.]))
        self.assertEqual(display_from_config({})[3],"auto_125_upper")
        self.assertEqual(display_from_config({"display":{"contour_levels":"auto_125"}})[3],
                         "auto_125_upper")

    def test_invalid_units_and_incomplete_pairs(self):
        for value, unit in [(-1,"g/s"),(1,"g"),(float("nan"),"kg/s")]:
            with self.assertRaises(ValueError):
                emission_to_kg_s(value,unit)
        with self.assertRaises(ValueError):
            emission_from_config({"emission_value":40})
