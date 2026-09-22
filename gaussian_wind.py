# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Wind regimes and weighted tables around the stationary Gaussian core."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import csv
import math

import numpy as np

try:  # package form used by the built QGIS plugin
    from .gaussian_core import (masters_2008_minimum_positive_x_m,
                                masters_2008_wind_speed_at_height)
except ImportError:  # standalone notebooks and scripts
    from gaussian_core import (masters_2008_minimum_positive_x_m,
                               masters_2008_wind_speed_at_height)

try:  # package form used by the built QGIS plugin
    from .gaussian_spatial import ground_concentration
except ImportError:  # standalone notebooks and scripts
    from gaussian_spatial import ground_concentration


WIND_MODES = ("constant", "fluctuating", "prevailing", "table")
ROSE_DIRECTION_SECTORS = 16
CALCULATION_DIRECTION_SECTORS = 72
SPEED_CLASS_EDGES_M_S = np.array(
    [0., 2., 4., 6., 8., 10., 12., np.inf])


def _finite(name, value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(name + " must be finite")
    return number


def _positive_integer(name, value):
    number = _finite(name, value)
    integer = int(number)
    if integer <= 0 or integer != number:
        raise ValueError(name + " must be a positive integer")
    return integer


def _nonnegative_integer(name, value):
    number = _finite(name, value)
    integer = int(number)
    if integer < 0 or integer != number:
        raise ValueError(name + " must be a nonnegative integer")
    return integer


@dataclass(frozen=True)
class WindSeries:
    mode: str
    directions_from_deg: np.ndarray
    speeds_m_s: np.ndarray
    weights: np.ndarray
    representative_from_deg: Optional[float]
    direction_std_deg: Optional[float]
    random_seed: Optional[int]
    description: str
    source_file: Optional[str] = None
    source_total_rows: Optional[int] = None
    excluded_calm_rows: int = 0
    excluded_variable_rows: int = 0
    excluded_missing_rows: int = 0

    @property
    def samples(self):
        return len(self.directions_from_deg)

    @property
    def mean_speed_m_s(self):
        return float(np.average(self.speeds_m_s, weights=self.weights))

    @property
    def resultant_length(self):
        angles = np.deg2rad(self.directions_from_deg)
        sine = np.average(np.sin(angles), weights=self.weights)
        cosine = np.average(np.cos(angles), weights=self.weights)
        return float(np.hypot(sine, cosine))


def _series(mode, directions, speeds, weights, representative, spread, seed,
            description, source_file=None, source_total_rows=None,
            excluded_calm_rows=0, excluded_variable_rows=0,
            excluded_missing_rows=0):
    directions = np.asarray(directions, dtype=float)
    speeds = np.asarray(speeds, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if (directions.ndim != 1 or not len(directions) or
            speeds.shape != directions.shape or weights.shape != directions.shape):
        raise ValueError("Wind directions, speeds and weights must be nonempty one-dimensional arrays of equal length")
    if (not np.all(np.isfinite(directions)) or not np.all(np.isfinite(speeds)) or
            not np.all(np.isfinite(weights))):
        raise ValueError("Wind table values must be finite")
    if np.any(speeds <= 0):
        raise ValueError("wind_speed_m_s must be positive; calm records require an explicit policy")
    if np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Wind weights must be nonnegative and have a positive sum")
    calm_rows = _nonnegative_integer("excluded_calm_rows", excluded_calm_rows)
    variable_rows = _nonnegative_integer(
        "excluded_variable_rows", excluded_variable_rows)
    missing_rows = _nonnegative_integer(
        "excluded_missing_rows", excluded_missing_rows)
    total_rows = (None if source_total_rows is None else
                  _positive_integer("source_total_rows", source_total_rows))
    if (total_rows is not None and
            calm_rows + variable_rows + missing_rows >= total_rows):
        raise ValueError(
            "Wind source counts must leave at least one directional observation")
    return WindSeries(mode, directions % 360, speeds, weights / weights.sum(),
                      representative, spread, seed, description, source_file,
                      total_rows, calm_rows, variable_rows, missing_rows)


def wind_observation_frequencies(wind):
    """Return source-category percentages used to annotate a wind rose.

    Missing rows are reported but excluded from the meteorological denominator.
    When no import metadata exists, all normalized wind weight is directional.
    """
    if wind.source_total_rows is None:
        return {"directional_percent": 100.0, "calm_percent": 0.0,
                "variable_percent": 0.0, "missing_rows": 0,
                "meteorological_rows": wind.samples,
                "directional_rows": wind.samples}
    directional_rows = (wind.source_total_rows - wind.excluded_calm_rows -
                        wind.excluded_variable_rows -
                        wind.excluded_missing_rows)
    meteorological_rows = wind.source_total_rows - wind.excluded_missing_rows
    if directional_rows <= 0 or meteorological_rows <= 0:
        raise ValueError("Wind source counts contain no usable observations")
    scale = 100.0 / meteorological_rows
    return {
        "directional_percent": directional_rows * scale,
        "calm_percent": wind.excluded_calm_rows * scale,
        "variable_percent": wind.excluded_variable_rows * scale,
        "missing_rows": wind.excluded_missing_rows,
        "meteorological_rows": meteorological_rows,
        "directional_rows": directional_rows,
    }


def _table_wind(model, base_dir):
    if "wind_file" not in model:
        raise ValueError("wind_mode table requires wind_file")
    path = Path(model["wind_file"]).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() if base_dir is None else Path(base_dir)) / path
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        required = {"direction_from_deg", "wind_speed_m_s"}
        if not required <= fields:
            raise ValueError("Wind table requires direction_from_deg and wind_speed_m_s columns")
        weight_field = "frequency_percent" if "frequency_percent" in fields else (
                       "weight" if "weight" in fields else None)
        count_fields = {"source_total_rows", "excluded_calm_rows",
                        "excluded_variable_rows", "excluded_missing_rows"}
        present_count_fields = count_fields & fields
        if present_count_fields and present_count_fields != count_fields:
            raise ValueError(
                "Wind table source-count metadata must include all four fields")
        if weight_field is None and "timestamp_utc" not in fields:
            raise ValueError(
                "Observation wind table requires timestamp_utc, "
                "direction_from_deg and wind_speed_m_s columns")
        directions, speeds, weights = [], [], []
        timestamps = set()
        source_counts = None
        for line, row in enumerate(reader, start=2):
            try:
                if weight_field is None:
                    timestamp_text = str(row["timestamp_utc"]).strip()
                    parsed = datetime.fromisoformat(
                        timestamp_text[:-1] + "+00:00"
                        if timestamp_text.endswith("Z") else timestamp_text)
                    if (parsed.utcoffset() is None or
                            parsed.utcoffset() != timedelta(0)):
                        raise ValueError(
                            f"timestamp_utc line {line} must specify UTC")
                    if parsed in timestamps:
                        raise ValueError(
                            f"timestamp_utc line {line} is duplicated")
                    timestamps.add(parsed)
                directions.append(_finite(f"direction_from_deg line {line}", row["direction_from_deg"]))
                speeds.append(_finite(f"wind_speed_m_s line {line}", row["wind_speed_m_s"]))
                weights.append(1.0 if weight_field is None else
                               _finite(f"{weight_field} line {line}", row[weight_field]))
                if present_count_fields:
                    counts = tuple(_nonnegative_integer(
                        f"{field} line {line}", row[field])
                        for field in ("source_total_rows", "excluded_calm_rows",
                                      "excluded_variable_rows",
                                      "excluded_missing_rows"))
                    if source_counts is None:
                        source_counts = counts
                    elif counts != source_counts:
                        raise ValueError(
                            "source-count metadata must be identical on every row")
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid wind table row {line}: {error}") from None
    if source_counts is not None:
        total, calm, variable, missing = source_counts
        if total != len(directions) + calm + variable + missing:
            raise ValueError(
                "source_total_rows must equal directional, calm, variable and missing rows")
    else:
        total, calm, variable, missing = None, 0, 0, 0
    table_kind = "observation" if weight_field is None else "weighted"
    provisional = _series("table", directions, speeds, weights, None, None, None,
                          table_kind + " wind table", str(path), total, calm,
                          variable, missing)
    angles = np.deg2rad(provisional.directions_from_deg)
    sine = np.average(np.sin(angles), weights=provisional.weights)
    cosine = np.average(np.cos(angles), weights=provisional.weights)
    representative = float(np.degrees(np.arctan2(sine, cosine)) % 360)
    return _series("table", directions, speeds, weights, representative, None, None,
                   f"{table_kind} wind table with {len(directions)} rows", str(path),
                   total, calm, variable, missing)


def wind_from_config(model, *, base_dir=None):
    """Build a synthetic regime or read a weighted/row-wise CSV wind table."""
    mode = str(model.get("wind_mode", "constant")).strip().lower()
    if mode not in WIND_MODES:
        raise ValueError("wind_mode must be constant, fluctuating, prevailing or table")
    if mode == "table":
        return _table_wind(model, base_dir)

    speed = _finite("wind_speed_m_s", model["wind_speed_m_s"])
    if speed <= 0:
        raise ValueError("wind_speed_m_s must be positive")
    centre = _finite("wind_from_deg", model.get("wind_from_deg", 0.0)) % 360
    if mode == "constant":
        return _series(mode, [centre], [speed], [1], centre, None, None,
                       f"constant wind from {centre:g}°")

    hours = _positive_integer("wind_hours", model.get("wind_hours", 1200))
    seed = _nonnegative_integer("wind_random_seed", model.get("wind_random_seed", 22001))
    rng = np.random.default_rng(seed)
    if mode == "fluctuating":
        directions = rng.uniform(0.0, 360.0, hours)
        return _series(mode, directions, np.full(hours, speed), np.ones(hours),
                       None, None, seed, "fluctuating wind direction from 0° to 360°")

    spread = _finite("wind_direction_std_deg", model.get("wind_direction_std_deg", 40.0))
    if spread <= 0:
        raise ValueError("wind_direction_std_deg must be positive")
    directions = np.mod(rng.normal(loc=centre, scale=spread, size=hours), 360.0)
    return _series(mode, directions, np.full(hours, speed), np.ones(hours),
                   centre, spread, seed,
                   f"prevailing wind from {centre:g}° with σ={spread:g}°")


def aggregate_wind_for_calculation(
        wind, direction_sectors=CALCULATION_DIRECTION_SECTORS):
    """Group wind into direction-speed classes for spatial calculation.

    The wind rose retains its independent 16-sector display. Within each
    calculation class, circular direction and harmonic speed preserve the
    weighted direction and the Gaussian equation's inverse-speed amplitude.
    """
    sectors = _positive_integer("direction_sectors", direction_sectors)
    if wind.samples == 1:
        return wind
    width = 360.0 / sectors
    direction_class = np.floor(
        (wind.directions_from_deg + width / 2.0) / width
    ).astype(int) % sectors
    speed_class = np.searchsorted(
        SPEED_CLASS_EDGES_M_S, wind.speeds_m_s, side="right") - 1
    speed_class = np.clip(
        speed_class, 0, len(SPEED_CLASS_EDGES_M_S) - 2)
    directions, speeds, weights = [], [], []
    for direction_index in range(sectors):
        for speed_index in range(len(SPEED_CLASS_EDGES_M_S) - 1):
            selected = ((direction_class == direction_index) &
                        (speed_class == speed_index))
            if not np.any(selected):
                continue
            selected_weights = wind.weights[selected]
            total_weight = float(selected_weights.sum())
            angles = np.deg2rad(wind.directions_from_deg[selected])
            direction = math.degrees(math.atan2(
                np.sum(selected_weights * np.sin(angles)),
                np.sum(selected_weights * np.cos(angles)))) % 360.0
            speed = total_weight / float(np.sum(
                selected_weights / wind.speeds_m_s[selected]))
            directions.append(direction)
            speeds.append(speed)
            weights.append(total_weight)
    return _series(
        wind.mode, directions, speeds, weights,
        wind.representative_from_deg, wind.direction_std_deg,
        wind.random_seed,
        f"{wind.description}; grouped into {sectors} calculation sectors",
        wind.source_file, wind.source_total_rows, wind.excluded_calm_rows,
        wind.excluded_variable_rows, wind.excluded_missing_rows)


def mean_ground_concentration(grid, wind, *, emission_kg_s,
                              effective_height_m, stability,
                              max_evaluations=None, progress_callback=None,
                              is_canceled=None,
                              direction_sectors=CALCULATION_DIRECTION_SECTORS,
                              wind_reference_height_m=None,
                              wind_exposure="rough"):
    """Return the weighted mean of stationary fields without changing the core."""
    calculation_wind = (wind if direction_sectors is None else
                        aggregate_wind_for_calculation(
                            wind, direction_sectors=direction_sectors))
    evaluations = int(np.prod(grid.shape)) * calculation_wind.samples
    if max_evaluations is not None and evaluations > max_evaluations:
        recommended = grid.resolution_m * math.sqrt(evaluations / max_evaluations)
        raise ValueError(
            "Wind averaging would evaluate {:,} cell-classes; the interactive "
            "limit is {:,}. Increase resolution to at least {:.0f} m or reduce "
            "the domain.".format(evaluations, max_evaluations,
                                 math.ceil(recommended)))
    total = np.zeros(grid.shape, dtype=float)
    wind_factor = 1.0
    if wind_reference_height_m is not None:
        wind_factor = float(masters_2008_wind_speed_at_height(
            1.0, wind_reference_height_m, effective_height_m,
            stability, wind_exposure))
    for index, (direction, speed, weight) in enumerate(zip(
            calculation_wind.directions_from_deg,
            calculation_wind.speeds_m_s,
            calculation_wind.weights), start=1):
        if is_canceled is not None and is_canceled():
            raise InterruptedError("Wind averaging canceled")
        total += weight * ground_concentration(grid, wind_from_deg=direction,
            emission_kg_s=emission_kg_s,
            wind_speed_m_s=speed * wind_factor,
            effective_height_m=effective_height_m, stability=stability,
            mask_near_source=False)
        if progress_callback is not None:
            progress_callback(index / calculation_wind.samples)
    minimum_x = masters_2008_minimum_positive_x_m(stability)
    east, north = np.meshgrid(grid.east_centres_m,
                              grid.north_centres_m)
    radius = np.hypot(east - grid.source.easting_m,
                      north - grid.source.northing_m)
    total[radius <= minimum_x] = np.nan
    return total


def save_wind_rose(wind, output_path, *, language="es"):
    """Save a separate frequency-by-direction-and-speed wind rose PNG."""
    # Plotting stays optional so the numerical wind layer can run in QGIS's
    # Python even when its bundled Matplotlib predates the colormaps registry.
    from matplotlib import cm
    from matplotlib.figure import Figure
    from matplotlib.ticker import PercentFormatter

    direction_width = 360.0 / ROSE_DIRECTION_SECTORS
    sector = np.floor((wind.directions_from_deg + direction_width / 2) /
                      direction_width).astype(int) % ROSE_DIRECTION_SECTORS
    speed_class = np.searchsorted(
        SPEED_CLASS_EDGES_M_S, wind.speeds_m_s, side="right") - 1
    speed_class = np.clip(speed_class, 0, len(SPEED_CLASS_EDGES_M_S) - 2)
    frequency = np.zeros(
        (ROSE_DIRECTION_SECTORS, len(SPEED_CLASS_EDGES_M_S) - 1))
    source_frequencies = wind_observation_frequencies(wind)
    np.add.at(frequency, (sector, speed_class),
              wind.weights * source_frequencies["directional_percent"])

    figure = Figure(figsize=(6.4, 6.4), constrained_layout=True)
    axis = figure.add_subplot(111, projection="polar")
    axis.set_theta_zero_location("N")
    axis.set_theta_direction(-1)
    theta = np.deg2rad(np.arange(ROSE_DIRECTION_SECTORS) * direction_width)
    bottom = np.zeros(ROSE_DIRECTION_SECTORS)
    colors = cm.Blues(np.linspace(.3, .95, frequency.shape[1]))
    labels = ["0–2", "2–4", "4–6", "6–8", "8–10", "10–12", "≥12"]
    for index, (color, label) in enumerate(zip(colors, labels)):
        axis.bar(theta, frequency[:, index], width=np.deg2rad(direction_width * .9),
                 bottom=bottom, color=color, edgecolor="white", linewidth=.5,
                 label=label)
        bottom += frequency[:, index]
    english = language == "en"
    axis.set_thetagrids(np.arange(0, 360, 45),
                        labels=["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                        if english else ["N", "NE", "E", "SE", "S", "SO", "O", "NO"])
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=1))
    axis.set_title("Wind rose · direction FROM" if english else
                   "Rosa de vientos · dirección DESDE", pad=22)
    if wind.source_total_rows is not None:
        calm_label = (("Calm" if english else "Calma") + "\n" +
                      f'{source_frequencies["calm_percent"]:.1f}%')
        axis.text(0.5, 0.5, calm_label, transform=axis.transAxes,
                  ha="center", va="center", fontsize=8,
                  bbox={"boxstyle": "circle,pad=.45", "facecolor": "white",
                        "edgecolor": "#4c78a8", "linewidth": .8})
        notes = [(("Variable" if english else "Variable") + ": " +
                  f'{source_frequencies["variable_percent"]:.1f}%')]
        if source_frequencies["missing_rows"]:
            notes.append(("Missing excluded" if english else "Ausentes excluidos") +
                         f': {source_frequencies["missing_rows"]}')
        axis.text(.01, .01, "\n".join(notes), transform=axis.transAxes,
                  ha="left", va="bottom", fontsize=8,
                  bbox={"boxstyle": "round,pad=.3", "facecolor": "white",
                        "edgecolor": "#aaaaaa", "alpha": .9})
    axis.legend(title="Speed (m/s)" if english else "Velocidad (m/s)",
                loc="lower left", bbox_to_anchor=(1.02, 0))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, transparent=False)
    figure.clear()
    return path
