import tempfile
from pathlib import Path
import unittest
import numpy as np
from pyproj import Transformer
from gaussian_spatial import locate_source,make_grid
from gaussian_raster import export_geotiff
from gaussian_contours import contour_levels,extract_isolines,upper_contour_level


class ContourTests(unittest.TestCase):
    def test_levels_follow_maximum_and_empty_cases(self):
        np.testing.assert_allclose(contour_levels(335,1), [1,2,5,10,20,50,100,200,300])
        self.assertTrue(np.all(contour_levels(20,.1)<20))
        self.assertEqual(len(contour_levels(0,.1)),0)
        self.assertEqual(len(contour_levels(.01,.1)),0)

    def test_automatic_125_and_manual_levels(self):
        np.testing.assert_allclose(contour_levels(425.3, 1), [1,2,5,10,20,50,100,200,400])
        np.testing.assert_allclose(contour_levels(425.3, 10), [10,20,50,100,200,400])
        np.testing.assert_allclose(contour_levels(335, 1, [1, 10, 50, 100, 500]),
                                   [1, 10, 50, 100])
        self.assertEqual(len(contour_levels(.101, .1)), 1)
        for maximum,expected in [(335,300),(630,600),(800,700),(2030,2000),(2330,2000),
                                 (.084,.08),(100,90)]:
            self.assertAlmostEqual(upper_contour_level(maximum),expected)

    def test_georeferenced_linear_field_and_labels(self):
        s=locate_source(-70.193195,-20.80532,calculation_crs=32719)
        g=make_grid(s,width_m=500,height_m=400,resolution_m=100)
        field=np.tile([0.,100.,200.,300.,400.],(4,1))
        with tempfile.TemporaryDirectory() as tmp:
            p=export_geotiff(Path(tmp)/"field.tif",g,field*1e-9,metadata={})
            lines,info=extract_isolines(p,minimum_display=50)
        self.assertAlmostEqual(info["maximum_ug_m3"],400,places=10)
        tr=Transformer.from_crs(4326,s.crs,always_xy=True)
        self.assertTrue(lines["features"])
        for f in lines["features"]:
            c=f["properties"]["concentration_ug_m3"]
            xy=np.array([tr.transform(*v) for v in f["geometry"]["coordinates"]])
            np.testing.assert_allclose(xy[:,0],g.east_centres_m[0]+c,atol=1e-6,rtol=0)
            le,ln=tr.transform(f["properties"]["label_longitude"],f["properties"]["label_latitude"])
            self.assertAlmostEqual(le,g.east_centres_m[0]+c,places=5)
            self.assertTrue(g.north_centres_m[-1]<=ln<=g.north_centres_m[0])

    def test_zero_field_has_no_spurious_contours(self):
        s=locate_source(-70.193195,-20.80532,calculation_crs=32719)
        g=make_grid(s,width_m=300,height_m=300,resolution_m=100)
        with tempfile.TemporaryDirectory() as tmp:
            p=export_geotiff(Path(tmp)/"zero.tif",g,np.zeros((3,3)),metadata={})
            lines,info=extract_isolines(p,minimum_display=.1)
        self.assertEqual(lines["features"],[])
        self.assertEqual(info["maximum_ug_m3"],0)
