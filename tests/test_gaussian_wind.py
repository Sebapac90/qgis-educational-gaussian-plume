import unittest
import tempfile
from pathlib import Path

import numpy as np

from gaussian_core import (briggs_final_plume_rise,
                           masters_2008_wind_speed_at_height)
from gaussian_spatial import ground_concentration, locate_source, make_grid
from gaussian_wind import (BriggsStackParameters,
                           CALCULATION_DIRECTION_SECTORS,
                           ROSE_DIRECTION_SECTORS, WindSeries,
                           aggregate_wind_for_calculation,
                           mean_ground_concentration, save_wind_rose,
                           wind_from_config, wind_observation_frequencies)


class WindTests(unittest.TestCase):
    def setUp(self):
        source = locate_source(-70.193195, -20.805320, calculation_crs=32719)
        self.grid = make_grid(source, width_m=600, height_m=600, resolution_m=100)
        self.model = {"wind_speed_m_s": 5, "wind_from_deg": 25}

    def test_constant_is_legacy_compatible(self):
        wind = wind_from_config(self.model)
        self.assertEqual(wind.mode, "constant")
        self.assertEqual(wind.directions_from_deg.tolist(), [25])
        averaged = mean_ground_concentration(self.grid, wind, emission_kg_s=.04,
            effective_height_m=50, stability="D")
        direct = ground_concentration(self.grid, wind_from_deg=25,
            emission_kg_s=.04, wind_speed_m_s=5, effective_height_m=50, stability="D")
        np.testing.assert_array_equal(averaged, direct)

    def test_seeded_fluctuating_and_prevailing_series(self):
        fluctuating = wind_from_config({**self.model, "wind_mode":"fluctuating",
            "wind_hours":1200, "wind_random_seed":22001})
        prevailing = wind_from_config({**self.model, "wind_mode":"prevailing",
            "wind_hours":1200, "wind_direction_std_deg":40, "wind_random_seed":22001})
        self.assertEqual(fluctuating.samples, 1200)
        self.assertTrue(np.all((fluctuating.directions_from_deg >= 0) &
                               (fluctuating.directions_from_deg < 360)))
        self.assertLess(fluctuating.resultant_length, .1)
        self.assertGreater(prevailing.resultant_length, .7)
        np.testing.assert_array_equal(fluctuating.directions_from_deg,
            wind_from_config({**self.model, "wind_mode":"fluctuating",
                "wind_hours":1200, "wind_random_seed":22001}).directions_from_deg)
        self.assertFalse(np.array_equal(fluctuating.directions_from_deg,
            wind_from_config({**self.model, "wind_mode":"fluctuating",
                "wind_hours":1200, "wind_random_seed":22002}).directions_from_deg))

    def test_average_is_mean_of_stationary_plumes(self):
        wind = WindSeries("fluctuating", np.array([0., 90.]), np.array([5., 5.]),
                          np.array([.5, .5]), None, None, 1, "test")
        actual = mean_ground_concentration(self.grid, wind, emission_kg_s=.04,
            effective_height_m=50, stability="D")
        expected = sum(ground_concentration(self.grid, wind_from_deg=direction,
            emission_kg_s=.04, wind_speed_m_s=5, effective_height_m=50, stability="D")
            for direction in (0., 90.)) / 2
        np.testing.assert_array_equal(actual, expected)

    def test_calculation_uses_finer_sectors_than_wind_rose(self):
        wind = wind_from_config({
            **self.model, "wind_mode": "prevailing", "wind_hours": 1200,
            "wind_from_deg": 225, "wind_direction_std_deg": 40,
            "wind_random_seed": 22001})
        grouped = aggregate_wind_for_calculation(wind)
        self.assertEqual(ROSE_DIRECTION_SECTORS, 16)
        self.assertEqual(CALCULATION_DIRECTION_SECTORS, 72)
        self.assertEqual(grouped.samples, 52)
        self.assertAlmostEqual(float(grouped.weights.sum()), 1.0)
        automatic = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04,
            effective_height_m=50, stability="D")
        explicit = mean_ground_concentration(
            self.grid, grouped, emission_kg_s=.04,
            effective_height_m=50, stability="D", direction_sectors=None)
        np.testing.assert_array_equal(automatic, explicit)

    def test_harmonic_speed_preserves_same_direction_concentration(self):
        wind = WindSeries(
            "table", np.array([10., 10.]), np.array([3., 3.5]),
            np.array([.25, .75]), 10., None, None, "test")
        grouped = aggregate_wind_for_calculation(wind)
        self.assertEqual(grouped.samples, 1)
        expected_speed = 1.0 / (.25 / 3.0 + .75 / 3.5)
        self.assertAlmostEqual(grouped.speeds_m_s[0], expected_speed)
        original = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04,
            effective_height_m=50, stability="D", direction_sectors=None)
        aggregated = mean_ground_concentration(
            self.grid, grouped, emission_kg_s=.04,
            effective_height_m=50, stability="D", direction_sectors=None)
        np.testing.assert_allclose(original, aggregated, rtol=1e-15)

    def test_work_limit_progress_and_cancel(self):
        wind = WindSeries("fluctuating", np.array([0., 90.]), np.array([5., 5.]),
                          np.array([.5, .5]), None, None, 1, "test")
        with self.assertRaisesRegex(ValueError, "interactive limit"):
            mean_ground_concentration(self.grid, wind, emission_kg_s=.04,
                effective_height_m=50, stability="D", max_evaluations=50)
        progress = []
        mean_ground_concentration(self.grid, wind, emission_kg_s=.04,
            effective_height_m=50, stability="D",
            progress_callback=progress.append)
        self.assertEqual(progress, [.5, 1.0])
        with self.assertRaises(InterruptedError):
            mean_ground_concentration(self.grid, wind, emission_kg_s=.04,
                effective_height_m=50, stability="D", is_canceled=lambda: True)

    def test_adjusts_wind_to_stack_height(self):
        wind = wind_from_config(self.model)
        unadjusted = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04, effective_height_m=50,
            stability="D")
        adjusted = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04, effective_height_m=50,
            stability="D",
            wind_reference_height_m=10, wind_exposure="rough")
        valid = np.isfinite(adjusted) & (unadjusted > 0)
        expected_factor = (50 / 10) ** .25
        np.testing.assert_allclose(
            adjusted[valid], unadjusted[valid] / expected_factor,
            rtol=1e-14)

    def test_briggs_uses_stack_wind_then_effective_height_wind(self):
        wind = wind_from_config(self.model)
        stack = BriggsStackParameters(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=10., stack_temperature_k=400.,
            ambient_temperature_k=300.)
        actual, summary = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04, stability="D",
            wind_reference_height_m=10., wind_exposure="rough",
            briggs_stack=stack, return_height_summary=True)
        stack_speed = float(masters_2008_wind_speed_at_height(
            5., 10., 50., "D", "rough"))
        plume = briggs_final_plume_rise(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=10., stack_temperature_k=400.,
            ambient_temperature_k=300., wind_speed_stack_m_s=stack_speed,
            stability="D")
        effective_speed = float(masters_2008_wind_speed_at_height(
            5., 10., plume.effective_height_m, "D", "rough"))
        expected = ground_concentration(
            self.grid, wind_from_deg=25., emission_kg_s=.04,
            wind_speed_m_s=effective_speed,
            effective_height_m=plume.effective_height_m, stability="D")
        np.testing.assert_allclose(actual, expected, rtol=1e-14)
        self.assertEqual(summary.mode, "briggs")
        self.assertAlmostEqual(summary.plume_rise_mean_m,
                               plume.plume_rise_m)
        self.assertAlmostEqual(summary.effective_height_mean_m,
                               plume.effective_height_m)
        self.assertAlmostEqual(summary.buoyancy_weight, 1.)
        self.assertAlmostEqual(summary.momentum_weight, 0.)

    def test_briggs_is_calculated_for_each_wind_speed_class(self):
        wind = WindSeries(
            "table", np.array([0., 90.]), np.array([2., 8.]),
            np.array([.25, .75]), None, None, None, "test")
        stack = BriggsStackParameters(
            stack_height_m=50., stack_diameter_m=2.,
            exit_velocity_m_s=10., stack_temperature_k=400.,
            ambient_temperature_k=300.)
        actual, summary = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04, stability="D",
            wind_reference_height_m=10., briggs_stack=stack,
            direction_sectors=None, return_height_summary=True)
        expected = np.zeros(self.grid.shape)
        rises = []
        heights = []
        for direction, speed, weight in zip(
                wind.directions_from_deg, wind.speeds_m_s, wind.weights):
            stack_speed = float(masters_2008_wind_speed_at_height(
                speed, 10., 50., "D", "rough"))
            plume = briggs_final_plume_rise(
                stack_height_m=50., stack_diameter_m=2.,
                exit_velocity_m_s=10., stack_temperature_k=400.,
                ambient_temperature_k=300.,
                wind_speed_stack_m_s=stack_speed, stability="D")
            effective_speed = float(masters_2008_wind_speed_at_height(
                speed, 10., plume.effective_height_m, "D", "rough"))
            expected += weight * ground_concentration(
                self.grid, wind_from_deg=direction, emission_kg_s=.04,
                wind_speed_m_s=effective_speed,
                effective_height_m=plume.effective_height_m, stability="D")
            rises.append(plume.plume_rise_m)
            heights.append(plume.effective_height_m)
        np.testing.assert_allclose(actual, expected, rtol=1e-14)
        self.assertNotAlmostEqual(rises[0], rises[1])
        self.assertAlmostEqual(
            summary.plume_rise_mean_m, np.average(rises, weights=wind.weights))
        self.assertAlmostEqual(
            summary.effective_height_mean_m,
            np.average(heights, weights=wind.weights))

    def test_briggs_grouping_stays_close_to_row_wise_calculation(self):
        rng = np.random.default_rng(718)
        samples = 600
        wind = WindSeries(
            "table", rng.normal(45., 35., samples) % 360.,
            np.clip(rng.lognormal(1.35, .45, samples), .4, 15.),
            np.full(samples, 1. / samples), None, None, None, "test")
        stack = BriggsStackParameters(50., 2., 10., 400., 300.)
        row_wise = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04, stability="D",
            wind_reference_height_m=10., briggs_stack=stack,
            direction_sectors=None)
        grouped = mean_ground_concentration(
            self.grid, wind, emission_kg_s=.04, stability="D",
            wind_reference_height_m=10., briggs_stack=stack)
        valid = (np.isfinite(row_wise) &
                 (row_wise > np.nanmax(row_wise) * .001))
        relative = np.abs(grouped[valid] - row_wise[valid]) / row_wise[valid]
        self.assertLess(float(np.max(relative)), .05)
        self.assertLess(
            abs(float(np.nanmax(grouped) / np.nanmax(row_wise) - 1.)), .02)

    def test_briggs_height_configuration_is_explicit(self):
        wind = wind_from_config(self.model)
        stack = BriggsStackParameters(50., 2., 10., 400., 300.)
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            mean_ground_concentration(
                self.grid, wind, emission_kg_s=.04,
                effective_height_m=50., stability="D", briggs_stack=stack)
        with self.assertRaisesRegex(ValueError, "required without"):
            mean_ground_concentration(
                self.grid, wind, emission_kg_s=.04, stability="D")
        with self.assertRaisesRegex(ValueError, "gradient"):
            mean_ground_concentration(
                self.grid, wind, emission_kg_s=.04, stability="E",
                briggs_stack=stack)

    def test_weighted_table_and_wind_rose(self):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "wind.csv"
            table.write_text("direction_from_deg,wind_speed_m_s,frequency_percent\n"
                             "0,2,25\n90,4,75\n", encoding="utf-8")
            wind = wind_from_config({"wind_mode":"table", "wind_file":str(table)})
            rose = save_wind_rose(wind, Path(directory) / "rose.png")
            self.assertEqual(rose.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(wind.mode, "table")
        np.testing.assert_allclose(wind.weights, [.25, .75])
        self.assertAlmostEqual(wind.mean_speed_m_s, 3.5)
        self.assertAlmostEqual(wind.representative_from_deg, 71.565051177)
        actual = mean_ground_concentration(self.grid, wind, emission_kg_s=.04,
            effective_height_m=50, stability="D")
        expected = (.25 * ground_concentration(self.grid, wind_from_deg=0,
                    emission_kg_s=.04, wind_speed_m_s=2,
                    effective_height_m=50, stability="D") +
                    .75 * ground_concentration(self.grid, wind_from_deg=90,
                    emission_kg_s=.04, wind_speed_m_s=4,
                    effective_height_m=50, stability="D"))
        np.testing.assert_allclose(actual, expected, rtol=1e-15)

    def test_observation_table_builds_equal_frequencies_and_validates_time(self):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "observations.csv"
            table.write_text(
                "timestamp_utc,direction_from_deg,wind_speed_m_s\n"
                "2025-01-01T00:00:00Z,0,2\n"
                "2025-01-01T01:00:00+00:00,90,4\n",
                encoding="utf-8")
            wind = wind_from_config(
                {"wind_mode": "table", "wind_file": str(table)})
            np.testing.assert_allclose(wind.weights, [.5, .5])

            for invalid_rows in (
                    "0,2\n90,4\n",
                    "2025-01-01T00:00:00,0,2\n"
                    "2025-01-01T01:00:00Z,90,4\n",
                    "2025-01-01T00:00:00Z,0,2\n"
                    "2025-01-01T00:00:00Z,90,4\n"):
                if invalid_rows.startswith("0,"):
                    header = "direction_from_deg,wind_speed_m_s\n"
                else:
                    header = ("timestamp_utc,direction_from_deg,"
                              "wind_speed_m_s\n")
                table.write_text(header + invalid_rows, encoding="utf-8")
                with self.assertRaises(ValueError):
                    wind_from_config(
                        {"wind_mode": "table", "wind_file": str(table)})

    def test_import_counts_scale_rose_and_survive_calculation_grouping(self):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "observations.csv"
            header = ("timestamp_utc,direction_from_deg,wind_speed_m_s,"
                      "source_total_rows,excluded_calm_rows,"
                      "excluded_variable_rows,excluded_missing_rows\n")
            table.write_text(
                header +
                "2025-01-01T00:00:00Z,0,2,10,2,1,1\n"
                "2025-01-01T01:00:00Z,90,4,10,2,1,1\n"
                "2025-01-01T02:00:00Z,180,6,10,2,1,1\n"
                "2025-01-01T03:00:00Z,270,8,10,2,1,1\n"
                "2025-01-01T04:00:00Z,45,3,10,2,1,1\n"
                "2025-01-01T05:00:00Z,225,5,10,2,1,1\n",
                encoding="utf-8")
            wind = wind_from_config(
                {"wind_mode": "table", "wind_file": str(table)})
            frequencies = wind_observation_frequencies(wind)
            self.assertEqual(frequencies["directional_rows"], 6)
            self.assertEqual(frequencies["meteorological_rows"], 9)
            self.assertAlmostEqual(frequencies["directional_percent"], 200 / 3)
            self.assertAlmostEqual(frequencies["calm_percent"], 200 / 9)
            self.assertAlmostEqual(frequencies["variable_percent"], 100 / 9)
            self.assertEqual(frequencies["missing_rows"], 1)
            grouped = aggregate_wind_for_calculation(wind)
            self.assertEqual(grouped.source_total_rows, 10)
            self.assertEqual(grouped.excluded_calm_rows, 2)
            self.assertEqual(grouped.excluded_variable_rows, 1)
            rose = save_wind_rose(wind, Path(directory) / "rose.png")
            self.assertEqual(rose.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_synthetic_hourly_table_is_used_before_rose(self):
        root = Path(__file__).resolve().parents[1]
        wind = wind_from_config({"wind_mode":"table",
            "wind_file":"examples/synthetic_wind_observations.csv"}, base_dir=root)
        self.assertEqual(wind.samples, 1200)
        np.testing.assert_allclose(wind.weights, np.full(1200, 1/1200))
        self.assertTrue(4 < wind.mean_speed_m_s < 6)
        circular_distance_from_north = min(wind.representative_from_deg,
                                           360-wind.representative_from_deg)
        self.assertLess(circular_distance_from_north, 5)
        self.assertGreater(wind.resultant_length, .5)

    def test_ne_sw_example_is_strongly_concentrated(self):
        root = Path(__file__).resolve().parents[1]
        wind = wind_from_config({"wind_mode":"table",
            "wind_file":"examples/synthetic_ne_sw_wind.csv"}, base_dir=root)
        self.assertEqual(wind.samples, 1200)
        difference = abs((wind.representative_from_deg - 45 + 180) % 360 - 180)
        self.assertLess(difference, 2)
        self.assertGreater(wind.resultant_length, .8)
        northeast = abs((wind.directions_from_deg - 45 + 180) % 360 - 180)
        southwest = abs((wind.directions_from_deg - 225 + 180) % 360 - 180)
        self.assertEqual(int(np.count_nonzero(northeast < southwest)), 1104)

    def test_invalid_wind_configuration(self):
        invalid = [
            {**self.model, "wind_mode":"unknown"},
            {**self.model, "wind_speed_m_s":0},
            {**self.model, "wind_mode":"fluctuating", "wind_hours":0},
            {**self.model, "wind_mode":"prevailing", "wind_direction_std_deg":0},
            {"wind_mode":"table"},
        ]
        for model in invalid:
            with self.subTest(model=model), self.assertRaises(ValueError):
                wind_from_config(model)
