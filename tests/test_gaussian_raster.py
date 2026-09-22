import tempfile
from pathlib import Path
import unittest
import numpy as np
import rasterio
from rasterio.transform import rowcol
from pyproj import Transformer
from gaussian_spatial import locate_source, make_grid
from gaussian_raster import export_geotiff, web_preview, NODATA


class RasterTests(unittest.TestCase):
    def test_round_trip_values_edges_and_source_pixel(self):
        s=locate_source(-70.193195,-20.805320,calculation_crs=32719)
        g=make_grid(s,width_m=500,height_m=300,resolution_m=100)
        data=np.arange(15,dtype=float).reshape(3,5)*1e-9
        with tempfile.TemporaryDirectory() as directory:
            path=export_geotiff(Path(directory)/"test.tif",g,data,metadata={"wind_from_deg":0})
            with rasterio.open(path) as r:
                self.assertEqual(r.crs.to_epsg(),32719)
                self.assertEqual(r.shape,(3,5))
                self.assertEqual(tuple(r.bounds),g.bounds)
                self.assertEqual(r.index(s.easting_m,s.northing_m),(1,2))
                np.testing.assert_allclose(r.xy(0,0),[g.east_centres_m[0],g.north_centres_m[0]])
                np.testing.assert_allclose(r.read(1),data*1e9,rtol=0,atol=0)
                self.assertEqual(r.nodata,NODATA)
                self.assertTrue(np.all(r.read_masks(1)==255))  # zero is valid
                self.assertEqual(r.tags(1)["units"],"ug/m3")
            preview,bounds,transform=web_preview(path)
            e,n=Transformer.from_crs(4326,3857,always_xy=True).transform(s.longitude_deg,s.latitude_deg)
            row,col=rowcol(transform,e,n)
            self.assertAlmostEqual(preview[row,col],7.)
            self.assertTrue(bounds[0][0]<s.latitude_deg<bounds[1][0])
            self.assertTrue(bounds[0][1]<s.longitude_deg<bounds[1][1])
            self.assertLess(transform.e,0)
            self.assertLess(preview[0,0],preview[-1,0])

    def test_configurable_concentration_unit(self):
        s=locate_source(-70.193195,-20.805320,calculation_crs=32719)
        g=make_grid(s,width_m=200,height_m=200,resolution_m=100)
        data=np.full((2,2),2e-6)
        with tempfile.TemporaryDirectory() as directory:
            path=export_geotiff(Path(directory)/"mg.tif",g,data,metadata={},
                                concentration_unit="mg/m3")
            with rasterio.open(path) as raster:
                np.testing.assert_allclose(raster.read(1),2.0,rtol=0,atol=0)
                self.assertEqual(raster.tags(1)["units"],"mg/m3")

    def test_nan_is_nodata_and_zero_remains_valid(self):
        s=locate_source(-70.193195,-20.805320,calculation_crs=32719)
        g=make_grid(s,width_m=200,height_m=200,resolution_m=100)
        data=np.array([[np.nan, 0.], [1e-9, 2e-9]])
        with tempfile.TemporaryDirectory() as directory:
            path=export_geotiff(Path(directory)/"nodata.tif",g,data,
                                metadata={})
            with rasterio.open(path) as raster:
                values=raster.read(1)
                mask=raster.read_masks(1)
                self.assertEqual(values[0,0],NODATA)
                self.assertEqual(mask[0,0],0)
                self.assertEqual(values[0,1],0.)
                self.assertEqual(mask[0,1],255)
