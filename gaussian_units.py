"""Explicit mass-rate and concentration conversions around the SI core."""
import math


_RATE_TO_KG_S = {
    "kg/s": 1.0,
    "g/s": 1e-3,
    "mg/s": 1e-6,
    "ug/s": 1e-9,
}

_CONCENTRATION_FROM_KG_M3 = {
    "kg/m3": 1.0,
    "g/m3": 1e3,
    "mg/m3": 1e6,
    "ug/m3": 1e9,
}


def canonical_unit(unit):
    """Return an ASCII unit token while accepting micro symbols and m³."""
    return str(unit).strip().lower().replace("µ", "u").replace("μ", "u").replace("³", "3")


def unit_label(unit):
    """Human-readable unit label for maps and metadata."""
    canonical = canonical_unit(unit)
    return canonical.replace("ug", "µg").replace("m3", "m³")


def emission_to_kg_s(value, unit):
    """Convert a finite, nonnegative emission rate to kg/s."""
    canonical = canonical_unit(unit)
    if canonical not in _RATE_TO_KG_S:
        raise ValueError("emission_unit must be kg/s, g/s, mg/s or ug/s")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("emission_value must be finite and nonnegative")
    return number * _RATE_TO_KG_S[canonical]


def concentration_factor_from_kg_m3(unit):
    """Multiplier from kg/m³ to the requested concentration unit."""
    canonical = canonical_unit(unit)
    if canonical not in _CONCENTRATION_FROM_KG_M3:
        raise ValueError("concentration_unit must be kg/m3, g/m3, mg/m3 or ug/m3")
    return _CONCENTRATION_FROM_KG_M3[canonical]


def concentration_factor_between(source_unit, target_unit):
    """Multiplier between supported concentration units."""
    source = concentration_factor_from_kg_m3(source_unit)
    target = concentration_factor_from_kg_m3(target_unit)
    return target / source


def emission_from_config(model):
    """Read the new value/unit pair, with legacy emission_g_s compatibility."""
    has_new = "emission_value" in model or "emission_unit" in model
    if has_new:
        if "emission_value" not in model or "emission_unit" not in model:
            raise ValueError("Define emission_value and emission_unit together")
        value, unit = model["emission_value"], canonical_unit(model["emission_unit"])
    elif "emission_g_s" in model:
        value, unit = model["emission_g_s"], "g/s"
    else:
        raise ValueError("Define emission_value/emission_unit (or legacy emission_g_s)")
    return float(value), unit, emission_to_kg_s(value, unit)


def display_from_config(config):
    """Read flexible display settings, preserving the old µg/m³ scenario."""
    display = config.get("display", {})
    unit = canonical_unit(display.get("concentration_unit", "ug/m3"))
    concentration_factor_from_kg_m3(unit)  # validate
    legacy = config.get("display_min_ug_m3", 0.1)
    raster_minimum = float(display.get("raster_minimum", legacy))
    contour_minimum = float(display.get("contour_minimum", raster_minimum))
    if not math.isfinite(raster_minimum) or raster_minimum <= 0:
        raise ValueError("raster_minimum must be finite and positive")
    if not math.isfinite(contour_minimum) or contour_minimum <= 0:
        raise ValueError("contour_minimum must be finite and positive")
    levels = display.get("contour_levels", "auto_125_upper")
    if levels == "auto_125":  # compatible with scenarios written before the upper-level rule
        levels = "auto_125_upper"
    if levels != "auto_125_upper":
        try:
            levels = [float(value) for value in levels]
        except (TypeError, ValueError):
            raise ValueError("contour_levels must be auto_125_upper or a list of positive values") from None
        if not levels or any(not math.isfinite(value) or value <= 0 for value in levels):
            raise ValueError("manual contour levels must be finite and positive")
        levels = sorted(set(levels))
    return unit, raster_minimum, contour_minimum, levels
