# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Steady point-source Gaussian plume, independent of GIS.

Inputs: metres, kg/s, m/s. Output: kg/m³. Coordinates are already in the
plume frame: x positive downwind, y crosswind, z above flat ground.
Dispersion follows Masters and Ela (2008), equations 7.47-7.48 and Table 7.8,
which reproduce the rural coefficients published by Martin (1976).
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np


STABILITY_CLASSES = tuple("ABCDEF")

# Masters and Ela (2008), equations 7.47-7.48 and Table 7.8.
# x is converted to km before applying these coefficients; sigmas are metres.
_MASTERS_LATERAL = {
    "A": 213.0, "B": 156.0, "C": 104.0,
    "D": 68.0, "E": 50.5, "F": 34.0,
}
_MASTERS_VERTICAL = {
    "A": ((440.8, 1.941, 9.27), (459.7, 2.094, -9.6)),
    "B": ((106.6, 1.149, 3.3), (108.2, 1.098, 2.0)),
    "C": ((61.0, .911, 0.0), (61.0, .911, 0.0)),
    "D": ((33.2, .725, -1.7), (44.5, .516, -13.0)),
    "E": ((22.8, .678, -1.3), (55.4, .305, -34.0)),
    "F": ((14.35, .740, -.35), (62.6, .180, -48.6)),
}
_MASTERS_WIND_EXPONENT_ROUGH = {
    "A": .15, "B": .15, "C": .20,
    "D": .25, "E": .40, "F": .60,
}
MASTERS_2008_FIGURE_START_M = 100.0
BRIGGS_GRAVITY_M_S2 = 9.8


@dataclass(frozen=True)
class BriggsPlumeRise:
    """Final Briggs plume-rise calculation in SI units."""

    method: str
    regime: str
    buoyancy_flux_m4_s3: float
    momentum_flux_m4_s2: float
    stability_parameter_s2: Optional[float]
    crossover_temperature_k: Optional[float]
    distance_to_final_rise_m: Optional[float]
    stack_tip_downwash_m: float
    corrected_stack_height_m: float
    plume_rise_m: float
    effective_height_m: float


def _category(stability):
    if not isinstance(stability, str) or stability not in STABILITY_CLASSES:
        raise ValueError("stability must be one of A, B, C, D, E, F")
    return stability


def _finite(name, value):
    array = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(array)):
        raise ValueError(name + " must contain only finite values")
    return array


def _scalar(name, value, strictly_positive=False):
    array = _finite(name, value)
    if array.ndim != 0 or array < 0 or (strictly_positive and array == 0):
        raise ValueError(name + " must be a scalar " +
                         ("> 0" if strictly_positive else ">= 0"))
    return float(array)


def _signed_scalar(name, value):
    array = _finite(name, value)
    if array.ndim != 0:
        raise ValueError(name + " must be a scalar")
    return float(array)


def masters_2008_dispersion_sigmas(x_m, stability):
    """Return Masters and Ela (2008) sigma_y and sigma_z in metres.

    Implements equations 7.47-7.48 with Table 7.8. Distance is received in
    metres and explicitly converted to kilometres. The <=1 km coefficients
    are used at the shared 1 km boundary. No artificial upper cap is applied.

    Figure 7.50 begins at 10^2 m, so shorter positive distances are an
    extrapolation. They remain calculable only while both sigmas are positive;
    nonpositive results are rejected rather than clipped.
    """
    category = _category(stability)
    x = _finite("x_m", x_m)
    if np.any(x <= 0):
        raise ValueError("masters_2008_dispersion_sigmas requires x_m > 0")
    x_km = x / 1000.0
    sy = _MASTERS_LATERAL[category] * x_km ** .894
    near = x_km <= 1.0
    near_c, near_d, near_f = _MASTERS_VERTICAL[category][0]
    far_c, far_d, far_f = _MASTERS_VERTICAL[category][1]
    sz = np.where(
        near,
        near_c * x_km ** near_d + near_f,
        far_c * x_km ** far_d + far_f,
    )
    if np.any(sz <= 0):
        raise ValueError(
            "x_m is below the positive range of the Masters 2008 sigma_z fit")
    return sy, sz


def masters_2008_minimum_positive_x_m(stability):
    """Shortest x where the Table 7.8 near-field sigma_z is positive.

    This is the exact zero of ``c*x**d + f`` in metres when ``f < 0``.
    Classes A-C have a positive sigma_z for every x > 0, so their limit is
    the source-plane singularity at zero. No empirical cutoff is introduced.
    """
    category = _category(stability)
    c, d, f = _MASTERS_VERTICAL[category][0]
    return 0.0 if f >= 0 else 1000.0 * (-f / c) ** (1.0 / d)


def masters_2008_wind_speed_at_height(
        wind_speed_ref_m_s, reference_height_m, target_height_m,
        stability, exposure="rough"):
    """Adjust observed wind speed to a target height using equation 7.46.

    ``stability`` is supplied explicitly by the student. ``exposure`` is
    ``rough`` for the Table 7.6 exponents or ``flat`` for the book's 0.6
    multiplier. Speeds may be arrays; both heights are positive scalars.
    """
    category = _category(stability)
    speed = _finite("wind_speed_ref_m_s", wind_speed_ref_m_s)
    if np.any(speed <= 0):
        raise ValueError("wind_speed_ref_m_s must be > 0")
    reference_height = _scalar(
        "reference_height_m", reference_height_m, strictly_positive=True)
    target_height = _scalar(
        "target_height_m", target_height_m, strictly_positive=True)
    if exposure not in ("rough", "flat"):
        raise ValueError("exposure must be rough or flat")
    exponent = _MASTERS_WIND_EXPONENT_ROUGH[category]
    if exposure == "flat":
        exponent *= .6
    return speed * (target_height / reference_height) ** exponent


def briggs_buoyancy_flux(exit_velocity_m_s, stack_diameter_m,
                         stack_temperature_k, ambient_temperature_k):
    """Return the Briggs buoyancy flux ``F_b`` in m^4/s^3.

    This is ISC3 equation 1-8 and is algebraically equivalent to Masters and
    Ela (2008), equation 7.52, after substituting ``r = d/2``.
    """
    velocity = _scalar(
        "exit_velocity_m_s", exit_velocity_m_s, strictly_positive=True)
    diameter = _scalar(
        "stack_diameter_m", stack_diameter_m, strictly_positive=True)
    stack_temperature = _scalar(
        "stack_temperature_k", stack_temperature_k, strictly_positive=True)
    ambient_temperature = _scalar(
        "ambient_temperature_k", ambient_temperature_k,
        strictly_positive=True)
    return (BRIGGS_GRAVITY_M_S2 * velocity * diameter ** 2 *
            (stack_temperature - ambient_temperature) /
            (4.0 * stack_temperature))


def briggs_momentum_flux(exit_velocity_m_s, stack_diameter_m,
                         stack_temperature_k, ambient_temperature_k):
    """Return the Briggs momentum flux ``F_m`` in m^4/s^2 (ISC3 1-9)."""
    velocity = _scalar(
        "exit_velocity_m_s", exit_velocity_m_s, strictly_positive=True)
    diameter = _scalar(
        "stack_diameter_m", stack_diameter_m, strictly_positive=True)
    stack_temperature = _scalar(
        "stack_temperature_k", stack_temperature_k, strictly_positive=True)
    ambient_temperature = _scalar(
        "ambient_temperature_k", ambient_temperature_k,
        strictly_positive=True)
    return (velocity ** 2 * diameter ** 2 * ambient_temperature /
            (4.0 * stack_temperature))


def briggs_stability_parameter(ambient_temperature_k,
                                ambient_temperature_gradient_k_m):
    """Return stable-atmosphere parameter ``s`` in s^-2.

    ``ambient_temperature_gradient_k_m`` follows the Masters sign convention:
    positive when ambient temperature increases with height. The added
    0.01 K/m converts the actual temperature gradient to the approximate
    potential-temperature gradient used in equation 7.53.
    """
    ambient_temperature = _scalar(
        "ambient_temperature_k", ambient_temperature_k,
        strictly_positive=True)
    gradient = _signed_scalar(
        "ambient_temperature_gradient_k_m",
        ambient_temperature_gradient_k_m)
    parameter = (BRIGGS_GRAVITY_M_S2 / ambient_temperature *
                 (gradient + 0.01))
    if parameter <= 0:
        raise ValueError(
            "ambient temperature gradient must produce stability parameter > 0")
    return parameter


def briggs_final_plume_rise(
        *, stack_height_m, stack_diameter_m, exit_velocity_m_s,
        stack_temperature_k, ambient_temperature_k, wind_speed_stack_m_s,
        stability, ambient_temperature_gradient_k_m=None,
        stack_tip_downwash=False):
    """Calculate final effective height with the Briggs ISC3 equations.

    Classes A-D select automatically between buoyancy and momentum using ISC3
    equations 1-10 through 1-16. Classes E-F additionally require the actual
    ambient temperature gradient in K/m and use equations 1-17 through 1-21.
    Final rise is returned; distance-dependent gradual rise is not applied.
    """
    category = _category(stability)
    stack_height = _scalar("stack_height_m", stack_height_m)
    diameter = _scalar(
        "stack_diameter_m", stack_diameter_m, strictly_positive=True)
    velocity = _scalar(
        "exit_velocity_m_s", exit_velocity_m_s, strictly_positive=True)
    stack_temperature = _scalar(
        "stack_temperature_k", stack_temperature_k, strictly_positive=True)
    ambient_temperature = _scalar(
        "ambient_temperature_k", ambient_temperature_k,
        strictly_positive=True)
    wind_speed = _scalar(
        "wind_speed_stack_m_s", wind_speed_stack_m_s,
        strictly_positive=True)
    if not isinstance(stack_tip_downwash, (bool, np.bool_)):
        raise ValueError("stack_tip_downwash must be boolean")

    buoyancy_flux = briggs_buoyancy_flux(
        velocity, diameter, stack_temperature, ambient_temperature)
    momentum_flux = briggs_momentum_flux(
        velocity, diameter, stack_temperature, ambient_temperature)
    delta_temperature = stack_temperature - ambient_temperature

    downwash = 0.0
    if stack_tip_downwash and velocity < 1.5 * wind_speed:
        downwash = 2.0 * diameter * (velocity / wind_speed - 1.5)
    corrected_height = stack_height + downwash
    if corrected_height < 0:
        raise ValueError("stack-tip downwash makes corrected stack height < 0")

    stability_parameter = None
    crossover = None
    final_distance = None
    if category in "ABCD":
        if delta_temperature > 0:
            if buoyancy_flux < 55.0:
                crossover = (0.0297 * stack_temperature *
                             velocity ** (1.0 / 3.0) /
                             diameter ** (2.0 / 3.0))
            else:
                crossover = (0.00575 * stack_temperature *
                             velocity ** (2.0 / 3.0) /
                             diameter ** (1.0 / 3.0))
        if delta_temperature > 0 and delta_temperature >= crossover:
            regime = "buoyancy"
            if buoyancy_flux < 55.0:
                final_distance = 49.0 * buoyancy_flux ** (5.0 / 8.0)
                rise = (21.425 * buoyancy_flux ** (3.0 / 4.0) /
                        wind_speed)
            else:
                final_distance = 119.0 * buoyancy_flux ** (2.0 / 5.0)
                rise = (38.71 * buoyancy_flux ** (3.0 / 5.0) /
                        wind_speed)
        else:
            regime = "momentum"
            rise = 3.0 * diameter * velocity / wind_speed
    else:
        if ambient_temperature_gradient_k_m is None:
            raise ValueError(
                "classes E-F require ambient_temperature_gradient_k_m")
        stability_parameter = briggs_stability_parameter(
            ambient_temperature, ambient_temperature_gradient_k_m)
        if delta_temperature > 0:
            crossover = (0.019582 * stack_temperature * velocity *
                         np.sqrt(stability_parameter))
        if delta_temperature > 0 and delta_temperature >= crossover:
            regime = "buoyancy"
            final_distance = (2.0715 * wind_speed /
                              np.sqrt(stability_parameter))
            rise = 2.6 * (buoyancy_flux /
                          (wind_speed * stability_parameter)) ** (1.0 / 3.0)
        else:
            regime = "momentum"
            stable_rise = 1.5 * (momentum_flux /
                                 (wind_speed *
                                  np.sqrt(stability_parameter))) ** (1.0 / 3.0)
            neutral_rise = 3.0 * diameter * velocity / wind_speed
            rise = min(stable_rise, neutral_rise)

    effective_height = corrected_height + rise
    return BriggsPlumeRise(
        method="briggs_isc3_final",
        regime=regime,
        buoyancy_flux_m4_s3=float(buoyancy_flux),
        momentum_flux_m4_s2=float(momentum_flux),
        stability_parameter_s2=(None if stability_parameter is None else
                                float(stability_parameter)),
        crossover_temperature_k=(None if crossover is None else
                                  float(crossover)),
        distance_to_final_rise_m=(None if final_distance is None else
                                  float(final_distance)),
        stack_tip_downwash_m=float(downwash),
        corrected_stack_height_m=float(corrected_height),
        plume_rise_m=float(rise),
        effective_height_m=float(effective_height),
    )


def gaussian_concentration(x_m, y_m, z_m, *, emission_kg_s,
                           wind_speed_m_s, effective_height_m, stability):
    """Concentration (kg/m³) from one continuous source over flat ground.

    x_m/y_m/z_m: finite broadcast-compatible coordinates in metres; z >= 0.
    emission_kg_s >= 0, wind_speed_m_s > 0, effective_height_m >= 0:
    finite scalars. Height is supplied, without a plume-rise calculation.
    stability: A/B/C/D/E/F. Perfect ground reflection.
    At x <= 0 return zero by convention, including the singular source plane.
    Returns a NumPy array with the broadcast shape (0-D for scalar inputs).
    No deposition, chemistry, terrain, time dependence, or GIS transformation.
    """
    category = _category(stability)
    q = _scalar("emission_kg_s", emission_kg_s)
    u = _scalar("wind_speed_m_s", wind_speed_m_s, strictly_positive=True)
    height = _scalar("effective_height_m", effective_height_m)
    x, y, z = np.broadcast_arrays(_finite("x_m", x_m),
                                   _finite("y_m", y_m), _finite("z_m", z_m))
    if np.any(z < 0):
        raise ValueError("z_m must be >= 0")
    result = np.zeros(x.shape, dtype=float)
    downwind = x > 0
    if not np.any(downwind):
        return result
    sy, sz = masters_2008_dispersion_sigmas(x[downwind], category)
    lateral = np.exp(-0.5 * (y[downwind] / sy) ** 2)
    direct = np.exp(-0.5 * ((z[downwind] - height) / sz) ** 2)
    reflected = np.exp(-0.5 * ((z[downwind] + height) / sz) ** 2)
    result[downwind] = q / (2 * np.pi * u * sy * sz) * lateral * (direct + reflected)
    return result
