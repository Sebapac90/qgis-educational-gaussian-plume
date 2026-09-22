import tempfile
from pathlib import Path
import unittest

from gaussian_map import contour_color_scale, create_map
from gaussian_raster import export_geotiff
from gaussian_spatial import ground_concentration, locate_source, make_grid


class MapTests(unittest.TestCase):
    def test_color_bands_change_at_contour_levels(self):
        boundaries,cmap,norm=contour_color_scale(335.26,.1,[1,2,5,10,20,50,100,200,300])
        self.assertEqual(boundaries.tolist(),[.1,1,2,5,10,20,50,100,200,300,335.26])
        self.assertEqual(cmap.N,10)
        self.assertEqual(norm(.2),norm(.9))
        self.assertNotEqual(norm(.9),norm(1.1))
        self.assertEqual(norm(201),norm(299))
        self.assertNotEqual(norm(299),norm(301))

    def test_wind_indicator_and_chimney_replace_map_direction_line(self):
        source=locate_source(-70.193195,-20.805320,calculation_crs=32719)
        grid=make_grid(source,width_m=1000,height_m=1000,resolution_m=100)
        concentration=ground_concentration(grid,wind_from_deg=0,
            emission_kg_s=.04,wind_speed_m_s=5,effective_height_m=50,stability="D")
        with tempfile.TemporaryDirectory() as directory:
            tif=export_geotiff(Path(directory)/"pluma.tif",grid,concentration,
                               metadata={},concentration_unit="ug/m3")
            map_view=create_map(tif,source,grid,wind_from_deg=0,
                display_min_ug_m3=.1,emission_g_s=40,wind_speed_m_s=5,
                height_m=50,stability="D",title="Prueba",contour_minimum=1)
            html=map_view.get_root().render()
        self.assertIn("source-chimney",html)
        self.assertIn(r"Direcci\u00f3n del viento",html)
        self.assertIn("wind-indicator",html)
        self.assertIn("rotate(180 22 24)",html)
        self.assertIn("bandas de isolíneas",html)
        self.assertNotIn("Avance de la pluma",html)

    def test_fluctuating_wind_has_no_directional_arrow(self):
        source=locate_source(-70.193195,-20.805320,calculation_crs=32719)
        grid=make_grid(source,width_m=1000,height_m=1000,resolution_m=100)
        concentration=ground_concentration(grid,wind_from_deg=0,
            emission_kg_s=.04,wind_speed_m_s=5,effective_height_m=50,stability="D")
        with tempfile.TemporaryDirectory() as directory:
            tif=export_geotiff(Path(directory)/"pluma.tif",grid,concentration,
                               metadata={},concentration_unit="ug/m3")
            map_view=create_map(tif,source,grid,wind_from_deg=0,
                display_min_ug_m3=.1,emission_g_s=40,wind_speed_m_s=5,
                height_m=50,stability="D",title="Prueba",contour_minimum=1,
                wind_mode="fluctuating",wind_samples=1200)
            html=map_view.get_root().render()
        self.assertIn("fluctuante · 0–360°",html)
        self.assertNotIn("rotate(180 22 24)",html)
