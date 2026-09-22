"""Vector isolines extracted in the raster CRS, then transformed to WGS84."""
import math
import numpy as np

try:  # package form used by the built QGIS plugin
    from .gaussian_units import canonical_unit, unit_label
except ImportError:  # standalone notebooks and scripts
    from gaussian_units import canonical_unit, unit_label


def upper_contour_level(maximum):
    """Highest one-significant-digit level strictly below a positive maximum."""
    maximum = float(maximum)
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("maximum must be finite and positive")
    magnitude = 10.0 ** math.floor(math.log10(maximum))
    leading = math.floor(maximum / magnitude)
    upper = leading * magnitude
    if math.isclose(upper, maximum, rel_tol=1e-12, abs_tol=0):
        upper = (leading - 1) * magnitude if leading > 1 else 9 * magnitude / 10
    return upper


def contour_levels(maximum, minimum_display, levels="auto_125_upper"):
    """Return 1–2–5 levels plus a rounded upper level, or manual levels."""
    threshold = float(minimum_display)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("minimum_display must be finite and positive")
    if not math.isfinite(maximum) or maximum < 0:
        raise ValueError("maximum must be finite and nonnegative")
    if maximum <= threshold:
        return np.array([], dtype=float)
    if levels == "auto_125":
        levels = "auto_125_upper"
    if levels != "auto_125_upper":
        candidates = np.asarray(levels, dtype=float)
        if candidates.ndim != 1 or len(candidates) == 0 or not np.all(np.isfinite(candidates)) or np.any(candidates <= 0):
            raise ValueError("manual contour levels must be finite and positive")
        return np.unique(candidates[(candidates >= threshold) &
                                    (candidates < maximum * (1-1e-12))])
    first_decade = math.floor(math.log10(threshold)) - 1
    last_decade = math.ceil(math.log10(maximum))
    candidates = np.array([multiplier * 10.0 ** decade
                           for decade in range(first_decade, last_decade + 1)
                           for multiplier in (1, 2, 5)])
    selected = candidates[(candidates >= threshold * (1-1e-12)) &
                          (candidates < maximum * (1-1e-12))]
    upper = upper_contour_level(maximum)
    if upper >= threshold * (1-1e-12) and upper < maximum * (1-1e-12):
        selected = np.r_[selected, upper]
    return np.unique(selected)


def extract_isolines(tif_path, *, minimum_display, levels="auto_125_upper"):
    """Return GeoJSON lines, actual maximum point, units and display levels.

    Contours interpolate between pixel centres in projected coordinates.
    No smoothing/extrapolation beyond outermost centres; open contours at
    the domain edge remain open. Reserved NoData pixels are masked.
    """
    import rasterio
    from matplotlib.figure import Figure
    from pyproj import Transformer

    with rasterio.open(tif_path) as src:
        values = src.read(1, masked=True)
        if values.count() == 0:
            raise ValueError("Raster contains no valid pixels")
        valid = values.compressed()
        if not np.all(np.isfinite(valid)) or np.any(valid < 0):
            raise ValueError("Concentrations must be finite and nonnegative")
        if src.crs is None or not src.crs.is_projected or src.transform.b != 0 or src.transform.d != 0:
            raise ValueError("Expected projected, axis-aligned raster")
        x = src.transform.c + (np.arange(src.width)+.5)*src.transform.a
        y = src.transform.f + (np.arange(src.height)+.5)*src.transform.e
        transform = Transformer.from_crs(src.crs, 4326, always_xy=True)
        maximum = float(values.max())
        row, col = np.unravel_index(np.ma.argmax(values), values.shape)
        max_lon, max_lat = transform.transform(x[col], y[row])
        unit = canonical_unit(src.tags(1).get("units", "ug/m3"))
        display_label = unit_label(unit)
        selected_levels = contour_levels(maximum, minimum_display, levels)
        features = []
        if min(values.shape) >= 2 and float(values.min()) < maximum and len(selected_levels):
            fig = Figure()
            ax = fig.subplots()
            contours = ax.contour(x, y, values, levels=selected_levels)
            for level_index, (level, segments) in enumerate(zip(contours.levels, contours.allsegs)):
                for segment in segments:
                    if len(segment) < 2 or not np.all(np.isfinite(segment)):
                        continue
                    distances = np.r_[0., np.cumsum(np.hypot(*np.diff(segment,axis=0).T))]
                    if distances[-1] <= 0:
                        continue
                    # Stagger label positions by level along the curve.
                    position = distances[-1] * (.25 + .1*(level_index % 5))
                    label_e = np.interp(position, distances, segment[:,0])
                    label_n = np.interp(position, distances, segment[:,1])
                    label_lon, label_lat = transform.transform(label_e, label_n)
                    lon, lat = transform.transform(segment[:,0], segment[:,1])
                    properties = {"concentration":float(level),
                            "concentration_unit":unit,
                            "label":f"{level:.4g}", "label_longitude":label_lon,
                            "label_latitude":label_lat, "length_m":float(distances[-1])}
                    if unit == "ug/m3":
                        properties["concentration_ug_m3"] = float(level)
                    features.append({"type":"Feature", "geometry":{
                        "type":"LineString", "coordinates":np.column_stack([lon,lat]).tolist()},
                        "properties":properties})
            fig.clear()
    return {"type":"FeatureCollection", "features":features}, {
        "maximum_ug_m3":maximum if unit == "ug/m3" else None, "maximum_latitude":max_lat,
        "maximum_longitude":max_lon, "maximum":maximum,
        "concentration_unit":unit, "concentration_unit_label":display_label,
        "levels":selected_levels.tolist(),
        "levels_ug_m3":selected_levels.tolist() if unit == "ug/m3" else None,
        "level_policy":"automatic_1_2_5_plus_upper" if levels in ("auto_125", "auto_125_upper") else "manual",
        "lowest_contour":float(selected_levels[0]) if len(selected_levels) else None,
        "lowest_contour_ug_m3":float(selected_levels[0]) if len(selected_levels) and unit == "ug/m3" else None}
