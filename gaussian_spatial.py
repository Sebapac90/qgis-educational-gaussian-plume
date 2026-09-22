"""Local flat-ground plume in a WGS84 UTM/UPS CRS; no QGIS dependency.

Wind input is meteorological FROM, clockwise from true north. UTM meridian
convergence at the source rotates it to grid north. Distances are projected
metres (local planar approximation); no elevation data are used.
"""
from dataclasses import dataclass, replace
import math
from typing import Optional

import numpy as np
from pyproj import CRS, Proj, Transformer
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info

try:  # package form used by the built QGIS plugin
    from .gaussian_core import (gaussian_concentration,
                                masters_2008_minimum_positive_x_m)
except ImportError:  # standalone notebooks and scripts
    from gaussian_core import (gaussian_concentration,
                               masters_2008_minimum_positive_x_m)


def finite_scalar(name, value):
    a = np.asarray(value, dtype=float)
    if a.ndim != 0 or not np.isfinite(a):
        raise ValueError(name + " must be a finite scalar")
    return float(a)


@dataclass(frozen=True)
class Source:
    longitude_deg: float
    latitude_deg: float
    easting_m: float
    northing_m: float
    crs: CRS
    convergence_deg: float
    input_crs: CRS = CRS.from_epsg(4326)
    input_x: Optional[float] = None
    input_y: Optional[float] = None


def _is_wgs84_metric_crs(crs):
    epsg = CRS.from_user_input(crs).to_epsg()
    return (epsg is not None and
            (32601 <= epsg <= 32660 or 32701 <= epsg <= 32760 or
             epsg in (32661, 32761)))


def automatic_calculation_crs(longitude_deg, latitude_deg):
    """Return a local WGS84 UTM CRS, or UPS beyond the UTM latitude limits."""
    lon = finite_scalar("longitude_deg", longitude_deg)
    lat = finite_scalar("latitude_deg", latitude_deg)
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("WGS84 longitude/latitude lies outside valid bounds")
    if lat > 84:
        return CRS.from_epsg(32661)
    if lat < -80:
        return CRS.from_epsg(32761)
    candidates = query_utm_crs_info(datum_name="WGS 84",
        area_of_interest=AreaOfInterest(lon, lat, lon, lat), contains=True)
    hemisphere = 326 if lat >= 0 else 327
    zone = min(60, max(1, math.floor((lon + 180) / 6) + 1))
    if 56 <= lat < 64 and 3 <= lon < 12:
        zone = 32
    elif 72 <= lat < 84:
        for west, east, special_zone in ((0, 9, 31), (9, 21, 33),
                                         (21, 33, 35), (33, 42, 37)):
            if west <= lon < east:
                zone = special_zone
                break
    preferred = f"{hemisphere}{zone:02d}"
    available = {info.code for info in candidates}
    if preferred not in available:
        matches = [info.code for info in candidates if info.code.startswith(str(hemisphere))]
        if not matches:
            raise ValueError("No WGS84 UTM CRS covers the source")
        preferred = matches[0]
    return CRS.from_epsg(int(preferred))


def locate_source(longitude_deg, latitude_deg, *, calculation_crs):
    """Project WGS84 lon/lat to an automatic or selected WGS84 UTM/UPS CRS.

    Reject geographic/feet/Web-Mercator CRSs and sources outside the projected
    CRS's published area of use. Input order is longitude, latitude.
    """
    lon = finite_scalar("longitude_deg", longitude_deg)
    lat = finite_scalar("latitude_deg", latitude_deg)
    crs = (automatic_calculation_crs(lon, lat) if calculation_crs == "auto"
           else CRS.from_user_input(calculation_crs))
    if not _is_wgs84_metric_crs(crs):
        raise ValueError("Use auto or a WGS84 UTM/UPS CRS in metres")
    area = crs.area_of_use
    if not (area.west <= lon <= area.east and area.south <= lat <= area.north):
        raise ValueError("Source lies outside the selected CRS area of use")
    transform = Transformer.from_crs(4326, crs, always_xy=True)
    east, north = transform.transform(lon, lat, errcheck=True)
    gamma = Proj(crs).get_factors(lon, lat, errcheck=True).meridian_convergence
    return Source(lon, lat, east, north, crs, gamma,
                  CRS.from_epsg(4326), lon, lat)


def locate_source_coordinates(x, y, *, input_crs, calculation_crs="auto"):
    """Locate a source supplied as WGS84 lon/lat or WGS84 UTM/UPS x/y."""
    input_x = finite_scalar("source x", x)
    input_y = finite_scalar("source y", y)
    source_crs = CRS.from_user_input(input_crs)
    if not source_crs.equals(CRS.from_epsg(4326)) and not _is_wgs84_metric_crs(source_crs):
        raise ValueError("Input CRS must be WGS84 (EPSG:4326) or WGS84 UTM/UPS")
    lon, lat = Transformer.from_crs(source_crs, 4326, always_xy=True).transform(
        input_x, input_y, errcheck=True)
    target = source_crs if calculation_crs == "auto" and source_crs.is_projected else calculation_crs
    located = locate_source(lon, lat, calculation_crs=target)
    return replace(located, input_crs=source_crs, input_x=input_x, input_y=input_y)


def locate_source_from_config(source_config):
    """Read canonical x/y/CRS coordinates, retaining the legacy lon/lat form."""
    if "coordinates" in source_config:
        coordinates = source_config["coordinates"]
        missing = {"x", "y", "crs"} - set(coordinates)
        if missing:
            raise ValueError("Source coordinates require x, y and crs")
        return locate_source_coordinates(coordinates["x"], coordinates["y"],
            input_crs=coordinates["crs"],
            calculation_crs=source_config.get("calculation_crs", "auto"))
    required = {"longitude_deg", "latitude_deg"}
    if not required <= set(source_config):
        raise ValueError("Source requires coordinates or legacy longitude_deg/latitude_deg")
    return locate_source(source_config["longitude_deg"], source_config["latitude_deg"],
                         calculation_crs=source_config.get("calculation_crs", "auto"))


def plume_coordinates(easting_m, northing_m, *, source_easting_m,
                      source_northing_m, wind_from_grid_deg):
    """(Downwind, signed crosswind) metres from projected E/N coordinates.

    Lower-level Cartesian transform: angle FROM is measured from GRID north.
    Source and receptor coordinates must already be in the same metric CRS.
    Roundoff within 32 machine epsilons times distance is snapped to zero,
    so exact crosswind/source-plane points do not create a tiny positive x.
    """
    east, north = np.broadcast_arrays(np.asarray(easting_m, dtype=float),
                                      np.asarray(northing_m, dtype=float))
    if not np.all(np.isfinite(east)) or not np.all(np.isfinite(north)):
        raise ValueError("Receptor coordinates must be finite")
    de = east - finite_scalar("source_easting_m", source_easting_m)
    dn = north - finite_scalar("source_northing_m", source_northing_m)
    angle = math.radians(finite_scalar("wind_from_grid_deg", wind_from_grid_deg) % 360)
    down = -math.sin(angle) * de - math.cos(angle) * dn
    cross = -math.cos(angle) * de + math.sin(angle) * dn
    tolerance = 32 * np.finfo(float).eps * np.maximum(1., np.hypot(de, dn))
    return (np.where(np.abs(down) <= tolerance, 0., down),
            np.where(np.abs(cross) <= tolerance, 0., cross))


@dataclass(frozen=True)
class Grid:
    source: Source
    resolution_m: float
    bounds: tuple  # west, south, east, north: OUTER pixel edges, metres
    east_centres_m: np.ndarray
    north_centres_m: np.ndarray

    @property
    def shape(self):
        return (len(self.north_centres_m), len(self.east_centres_m))


def make_grid(source, *, width_m, height_m, resolution_m):
    """Rectangular grid centred on source; rows north->south, cols west->east.

    Sample at pixel centres, not vertices. Dimensions must be exact multiples
    of resolution; no silent extension. Limit: 4 million cells, 100 km/side.
    """
    width = finite_scalar("width_m", width_m)
    height = finite_scalar("height_m", height_m)
    return make_grid_bounds(
        source, west_m=source.easting_m - width / 2,
        south_m=source.northing_m - height / 2,
        east_m=source.easting_m + width / 2,
        north_m=source.northing_m + height / 2,
        resolution_m=resolution_m)


def make_grid_bounds(source, *, west_m, south_m, east_m, north_m,
                     resolution_m):
    """Axis-aligned grid from outer pixel edges, preserving centre sampling."""
    west = finite_scalar("west_m", west_m)
    south = finite_scalar("south_m", south_m)
    east = finite_scalar("east_m", east_m)
    north = finite_scalar("north_m", north_m)
    res = finite_scalar("resolution_m", resolution_m)
    width, height = east - west, north - south
    if min(width, height, res) <= 0 or max(width, height) > 100000:
        raise ValueError("Use positive sizes and a local domain <= 100 km per side")
    nc, nr = round(width / res), round(height / res)
    if min(nc, nr) < 1 or not math.isclose(nc * res, width, abs_tol=1e-8) or not math.isclose(nr * res, height, abs_tol=1e-8):
        raise ValueError("Domain dimensions must be multiples of resolution")
    if nc * nr > 4_000_000:
        raise ValueError("Grid exceeds 4 million cells; increase resolution_m")
    return Grid(source, res, (west, south, east, north),
                west + (np.arange(nc) + .5)*res,
                north - (np.arange(nr) + .5)*res)


def ground_concentration(grid, *, wind_from_deg, emission_kg_s,
                         wind_speed_m_s, effective_height_m, stability,
                         mask_near_source=True):
    """Return 2-D ground concentration kg/m³; wind FROM true north in degrees.

    No default wind direction. The explicit scenario chooses the direction.
    Correct true->grid azimuth once at source; keep a uniform planar wind.
    """
    grid_angle = finite_scalar("wind_from_deg", wind_from_deg) - grid.source.convergence_deg
    east, north = np.meshgrid(grid.east_centres_m, grid.north_centres_m)
    down, cross = plume_coordinates(east, north,
        source_easting_m=grid.source.easting_m, source_northing_m=grid.source.northing_m,
        wind_from_grid_deg=grid_angle)
    # Apply the published equation unchanged wherever sigma_z is positive.
    # The stability-specific root is mathematical, not a rounded cutoff.
    minimum_x = masters_2008_minimum_positive_x_m(stability)
    concentration = np.zeros(grid.shape, dtype=float)
    valid_downwind = down > minimum_x
    if np.any(valid_downwind):
        concentration[valid_downwind] = gaussian_concentration(
            down[valid_downwind], cross[valid_downwind], 0.,
            emission_kg_s=emission_kg_s,
            wind_speed_m_s=wind_speed_m_s,
            effective_height_m=effective_height_m,
            stability=stability)
    if mask_near_source:
        radius = np.hypot(east - grid.source.easting_m,
                          north - grid.source.northing_m)
        concentration[radius <= minimum_x] = np.nan
    return concentration
