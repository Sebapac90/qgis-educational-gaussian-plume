"""Georeferenced output and Web Mercator preview; no physics or QGIS API."""
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin, array_bounds
from rasterio.warp import calculate_default_transform, reproject, transform_bounds, Resampling
from gaussian_units import canonical_unit, concentration_factor_from_kg_m3, unit_label

NODATA = -9999.0


def export_geotiff(path, grid, concentration_kg_m3, *, metadata, concentration_unit="ug/m3"):
    """Write float64 concentrations in a declared unit; retain all valid values.

    Conversion from the core's kg/m³ is explicit. No display threshold is
    applied. NaN cells are written as NoData=-9999; zero remains valid.
    """
    values = np.asarray(concentration_kg_m3, dtype=float)
    valid = np.isfinite(values)
    if (values.shape != grid.shape or np.any(np.isinf(values)) or
            np.any(values[valid] < 0)):
        raise ValueError(
            "Expected nonnegative concentration or NaN matching grid shape")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    west, south, east, north = grid.bounds
    transform = from_origin(west, north, grid.resolution_m, grid.resolution_m)
    unit = canonical_unit(concentration_unit)
    factor = concentration_factor_from_kg_m3(unit)
    label = unit_label(unit)
    with rasterio.open(path, "w", driver="GTiff", width=grid.shape[1], height=grid.shape[0],
                       count=1, dtype="float64", crs=grid.source.crs, transform=transform,
                       nodata=NODATA, compress="deflate") as dst:
        output = np.where(valid, values * factor, NODATA)
        dst.write(output, 1)
        dst.set_band_description(1, f"Ground concentration ({label})")
        dst.update_tags(**{k: str(v) for k,v in metadata.items()})
        dst.update_tags(1, units=unit, receptor_height_m="0", terrain="flat")
    return path


def web_preview(path):
    """Reproject GeoTIFF to EPSG:3857 before overlaying on a Leaflet map.

    Nearest neighbour retains cell values; preview does not change source TIFF.
    Returns values in the GeoTIFF's declared unit, Leaflet bounds and transform.
    """
    with rasterio.open(path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:3857", src.width, src.height, *src.bounds)
        preview = np.full((height, width), NODATA, dtype=float)
        reproject(source=rasterio.band(src, 1), destination=preview,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=transform, dst_crs="EPSG:3857", dst_nodata=NODATA,
                  resampling=Resampling.nearest)
    west, south, east, north = transform_bounds("EPSG:3857", "EPSG:4326",
                                               *array_bounds(height, width, transform))
    return preview, [[south, west], [north, east]], transform
