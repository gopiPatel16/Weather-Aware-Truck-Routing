"""Corridor grid in REAL distance and per-hour risk levels for the heatmap overview (plan 6).

A fixed-degree grid (e.g. 0.25 deg) is ~13 mi wide at 40 N but ~9 mi at 60 N, so it is NOT used.
Rows are ``cell_miles`` apart north-south; inside each row the longitude step is widened by
1/cos(latitude) so east-west spacing is also ``cell_miles``. Cell centres come from integer
(row, col) indices, so the lattice is global and deterministic (cache-friendly).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from trucking.config import HEATMAP_HOURS

from .forecast import HourlySeries, assess_selection, select_forecast
from .geo import MILES_PER_DEGREE, haversine_miles
from .types import LatLon, RiskLevel

UNKNOWN_CHAR = "9"


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    lat: float
    lon: float


def lat_step_deg(cell_miles: float) -> float:
    return cell_miles / MILES_PER_DEGREE


def lon_step_deg(lat: float, cell_miles: float) -> float:
    return cell_miles / (MILES_PER_DEGREE * math.cos(math.radians(lat)))


def corridor_cells(
    route_samples: Iterable[Sequence[LatLon]], cell_miles: float, half_width_miles: float
) -> list[Cell]:
    """Union of lattice cells whose centre is within ``half_width_miles`` of any sample point."""
    dlat = lat_step_deg(cell_miles)
    hw_lat = half_width_miles / MILES_PER_DEGREE
    cells: dict[tuple[int, int], Cell] = {}
    for samples in route_samples:
        for lat, lon in samples:
            for row in range(
                math.floor((lat - hw_lat) / dlat), math.ceil((lat + hw_lat) / dlat) + 1
            ):
                clat = row * dlat
                if abs(clat) > 85:
                    continue
                dlon = lon_step_deg(clat, cell_miles)
                hw_lon = half_width_miles / (MILES_PER_DEGREE * math.cos(math.radians(clat)))
                for col in range(
                    math.floor((lon - hw_lon) / dlon), math.ceil((lon + hw_lon) / dlon) + 1
                ):
                    if (row, col) in cells:
                        continue
                    clon = col * dlon
                    if haversine_miles((clat, clon), (lat, lon)) <= half_width_miles:
                        cells[(row, col)] = Cell(row, col, clat, clon)
    return sorted(cells.values(), key=lambda c: (c.row, c.col))


def hourly_levels(
    series: HourlySeries | None,
    departure_utc: datetime,
    cargo_lb: float,
    hours: int = HEATMAP_HOURS,
) -> list[RiskLevel | None]:
    """Risk level for hour h = 0..hours after departure, using the SAME interval policy and risk
    engine as the checkpoints. A cell without data is Unknown for every hour."""
    if series is None:
        return [None] * (hours + 1)
    levels: list[RiskLevel | None] = []
    for h in range(hours + 1):
        selection = select_forecast(series, departure_utc + timedelta(hours=h))
        assessment, _ = assess_selection(selection, cargo_lb)
        levels.append(assessment.level)
    return levels


def levels_string(levels: Sequence[RiskLevel | None]) -> str:
    """One character per hour: 0-4 = Low..No Travel, 9 = Unknown."""
    return "".join(UNKNOWN_CHAR if lv is None else str(int(lv)) for lv in levels)
