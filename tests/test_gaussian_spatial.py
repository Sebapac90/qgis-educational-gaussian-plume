import unittest
import numpy as np
from pyproj import Geod, Transformer
from gaussian_core import (gaussian_concentration,
                           masters_2008_minimum_positive_x_m)
from gaussian_spatial import (automatic_calculation_crs, ground_concentration,
                              locate_source, locate_source_coordinates,
                              locate_source_from_config, make_grid,
                              make_grid_bounds,
                              plume_coordinates)


class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.source = locate_source(-70.193195, -20.805320, calculation_crs=32719)

    def test_crs_round_trip(self):
        s = self.source
        lon, lat = Transformer.from_crs(s.crs, 4326, always_xy=True).transform(s.easting_m, s.northing_m)
        self.assertAlmostEqual(lon, s.longitude_deg, places=10)
        self.assertAlmostEqual(lat, s.latitude_deg, places=10)
        self.assertTrue(375000 < s.easting_m < 377000)
        self.assertTrue(7698000 < s.northing_m < 7700000)

    def test_wgs84_and_utm_inputs_locate_the_same_source(self):
        wgs84 = locate_source_coordinates(-70.193195, -20.805320,
            input_crs=4326, calculation_crs="auto")
        utm = locate_source_coordinates(wgs84.easting_m, wgs84.northing_m,
            input_crs=32719, calculation_crs="auto")
        self.assertEqual(wgs84.crs.to_epsg(), 32719)
        self.assertEqual(utm.crs.to_epsg(), 32719)
        self.assertAlmostEqual(utm.longitude_deg, wgs84.longitude_deg, places=9)
        self.assertAlmostEqual(utm.latitude_deg, wgs84.latitude_deg, places=9)
        self.assertAlmostEqual(utm.easting_m, wgs84.easting_m, places=6)
        self.assertAlmostEqual(utm.northing_m, wgs84.northing_m, places=6)
        gw = make_grid(wgs84,width_m=10000,height_m=10000,resolution_m=50)
        gu = make_grid(utm,width_m=10000,height_m=10000,resolution_m=50)
        cw = ground_concentration(gw,wind_from_deg=0,emission_kg_s=.04,
                                  wind_speed_m_s=5,effective_height_m=50,
                                  stability="D")
        cu = ground_concentration(gu,wind_from_deg=0,emission_kg_s=.04,
                                  wind_speed_m_s=5,effective_height_m=50,
                                  stability="D")
        # A WGS84 -> UTM -> WGS84 round trip shifts projected coordinates by
        # sub-nanometres. Bound its effect far below any displayable value.
        np.testing.assert_allclose(cu,cw,rtol=1e-9,atol=1e-18)
        configured = locate_source_from_config({"coordinates":{
            "crs":"EPSG:32719", "x":utm.easting_m, "y":utm.northing_m}})
        self.assertEqual(configured.input_crs.to_epsg(), 32719)

    def test_automatic_crs_is_global(self):
        cases = [
            (-74.0, 40.7, 32618),       # New York
            (151.2, -33.9, 32756),      # Sydney
            (139.7, 35.7, 32654),       # Tokyo
            (36.8, -1.3, 32737),        # Nairobi
            (6.0, 60.0, 32632),         # Norway exception
            (15.0, 78.0, 32633),        # Svalbard exception
            (0.0, 89.0, 32661),         # Arctic UPS
            (0.0, -89.0, 32761),        # Antarctic UPS
        ]
        for lon, lat, epsg in cases:
            with self.subTest(lon=lon,lat=lat):
                self.assertEqual(automatic_calculation_crs(lon,lat).to_epsg(),epsg)
                source=locate_source_coordinates(lon,lat,input_crs=4326,
                                                 calculation_crs="auto")
                self.assertEqual(source.crs.to_epsg(),epsg)

    def test_invalid_crs_location_and_grid(self):
        for crs in [4326, 3857, 2263, 32619, 32718]:
            with self.subTest(crs=crs), self.assertRaises(ValueError):
                locate_source(-70.193195, -20.805320, calculation_crs=crs)
        for width, res in [(100, 30), (-100, 10), (100, 0), (10000, 1)]:
            with self.subTest(width=width,res=res), self.assertRaises(ValueError):
                make_grid(self.source, width_m=width, height_m=10000, resolution_m=res)
        with self.assertRaises(ValueError):
            locate_source_coordinates(0,0,input_crs=3857)
        with self.assertRaises(ValueError):
            locate_source_from_config({"coordinates":{"crs":4326,"x":0}})

    def test_cardinal_and_oblique_grid_wind(self):
        for direction in [0, 45, 90, 135, 180, 225, 270, 315, 360, -90]:
            a = np.deg2rad(direction)
            de, dn = -1000*np.sin(a), -1000*np.cos(a)
            down, cross = plume_coordinates(de, dn, source_easting_m=0,
                source_northing_m=0, wind_from_grid_deg=direction)
            np.testing.assert_allclose([down, cross], [1000, 0], atol=1e-10)
            up, _ = plume_coordinates(-de, -dn, source_easting_m=0,
                source_northing_m=0, wind_from_grid_deg=direction)
            self.assertLess(up, 0)

    def test_true_north_convergence_against_geodesic(self):
        s = self.source
        tr = Transformer.from_crs(4326, s.crs, always_xy=True)
        for wind in [0, 45, 90, 180, 270]:
            # Independent true-bearing reference, 1 km towards the plume.
            lon, lat, _ = Geod(ellps="WGS84").fwd(s.longitude_deg, s.latitude_deg, wind+180, 1000)
            e, n = tr.transform(lon, lat)
            down, cross = plume_coordinates(e,n,source_easting_m=s.easting_m,
                source_northing_m=s.northing_m, wind_from_grid_deg=wind-s.convergence_deg)
            self.assertAlmostEqual(float(down), 1000, delta=.5)  # UTM local scale
            self.assertLess(abs(float(cross)), .01)

    def test_rectangular_pixel_centres_and_orientation(self):
        g = make_grid(self.source,width_m=600,height_m=400,resolution_m=100)
        self.assertEqual(g.shape,(4,6))
        self.assertEqual(g.east_centres_m[0],g.bounds[0]+50)
        self.assertEqual(g.north_centres_m[0],g.bounds[3]-50)
        self.assertEqual(g.north_centres_m[-1],g.bounds[1]+50)
        self.assertTrue(np.all(np.diff(g.north_centres_m)<0))

    def test_asymmetric_bounds_preserve_overlapping_pixel_centres(self):
        centred = make_grid(self.source, width_m=600, height_m=400,
                            resolution_m=100)
        west, south, east, north = centred.bounds
        extended = make_grid_bounds(
            self.source, west_m=west, south_m=south - 400,
            east_m=east, north_m=north, resolution_m=100)
        self.assertEqual(extended.shape, (8, 6))
        np.testing.assert_array_equal(extended.east_centres_m,
                                      centred.east_centres_m)
        np.testing.assert_array_equal(extended.north_centres_m[:4],
                                      centred.north_centres_m)
        self.assertEqual(extended.bounds, (west, south - 400, east, north))

        with self.assertRaises(ValueError):
            make_grid_bounds(self.source, west_m=west, south_m=south - 25,
                             east_m=east, north_m=north, resolution_m=100)

    def test_source_plane_and_translated_frame(self):
        d,c = plume_coordinates([500,500,600],[200,300,200],
            source_easting_m=500,source_northing_m=200,wind_from_grid_deg=0)
        np.testing.assert_array_equal(d,[0,-100,0])
        np.testing.assert_array_equal(c,[0,0,-100])

    def test_grid_matches_direct_core_evaluation_all_directions(self):
        g=make_grid(self.source,width_m=2000,height_m=3000,resolution_m=100)
        e,n=np.meshgrid(g.east_centres_m,g.north_centres_m)
        for wind in [0,45,90,180,270]:
            actual=ground_concentration(g,wind_from_deg=wind,emission_kg_s=.04,
                wind_speed_m_s=5,effective_height_m=50,stability="D")
            down,cross=plume_coordinates(e,n,
                source_easting_m=self.source.easting_m,
                source_northing_m=self.source.northing_m,
                wind_from_grid_deg=wind-self.source.convergence_deg)
            expected=np.zeros(g.shape)
            minimum=masters_2008_minimum_positive_x_m("D")
            valid=down>minimum
            expected[valid]=gaussian_concentration(
                down[valid],cross[valid],0.,emission_kg_s=.04,
                wind_speed_m_s=5,effective_height_m=50,stability="D")
            radius=np.hypot(e-self.source.easting_m,n-self.source.northing_m)
            expected[radius<=minimum]=np.nan
            np.testing.assert_allclose(actual,expected,rtol=1e-14,atol=0,
                                       equal_nan=True)
        self.assertEqual(actual.shape,(30,20))

    def test_masters_masks_source_and_calculates_beyond_near_field(self):
        g = make_grid(self.source, width_m=60, height_m=60,
                      resolution_m=10)
        concentration = ground_concentration(
            g, wind_from_deg=270, emission_kg_s=.04,
            wind_speed_m_s=5, effective_height_m=10, stability="D")
        east, north = np.meshgrid(g.east_centres_m, g.north_centres_m)
        radius = np.hypot(east-self.source.easting_m,
                          north-self.source.northing_m)
        minimum_x = masters_2008_minimum_positive_x_m("D")
        self.assertAlmostEqual(minimum_x, 16.5859017, places=6)
        self.assertTrue(np.all(np.isnan(
            concentration[radius <= minimum_x])))
        self.assertTrue(np.all(np.isfinite(
            concentration[radius > minimum_x])))
        self.assertGreater(np.nanmax(concentration), 0)
