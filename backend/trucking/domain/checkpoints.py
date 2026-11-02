"""Checkpoints every N miles with ETAs and midpoint segment ownership (plan 5.2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from trucking.config import INTERVAL_OPTIONS, MAX_CHECKPOINTS_PER_ROUTE

from .eta import TimeProfile
from .geo import METERS_PER_MILE, point_at
from .types import LatLon


@dataclass(frozen=True)
class Checkpoint:
    index: int
    mile: float
    lat: float
    lon: float
    eta_utc: datetime
    owns_from_mi: float  # the stretch of route this checkpoint's risk applies to
    owns_to_mi: float

    @property
    def owned_miles(self) -> float:
        return self.owns_to_mi - self.owns_from_mi


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """0, N, 2N, ... while d <= total - N/4, then always the destination.

    A regular checkpoint within a quarter interval of the end is dropped so the destination does
    not get a near-duplicate neighbour.
    """
    if total_mi <= 0 or interval_mi <= 0:
        raise ValueError("total and interval must be positive")
    miles = [0.0]
    k = 1
    while k * interval_mi <= total_mi - 0.25 * interval_mi + 1e-9:
        miles.append(k * interval_mi)
        k += 1
    miles.append(total_mi)
    return miles


def choose_interval(
    total_mi: float, requested: int, cap: int = MAX_CHECKPOINTS_PER_ROUTE
) -> tuple[int, bool]:
    """The requested interval, raised to the next option if it would exceed the checkpoint cap."""
    options = [o for o in sorted(INTERVAL_OPTIONS) if o >= requested]
    for option in options:
        if len(checkpoint_miles(total_mi, option)) <= cap:
            return option, option != requested
    return options[-1] if options else requested, True


def build_checkpoints(
    points: Sequence[LatLon],
    cumulative_mi: Sequence[float],
    profile: TimeProfile,
    departure_utc: datetime,
    interval_mi: float,
) -> list[Checkpoint]:
    """``cumulative_mi`` must already be scaled so its last value is the route length."""
    total = cumulative_mi[-1]
    miles = checkpoint_miles(total, interval_mi)
    checkpoints: list[Checkpoint] = []
    for i, mile in enumerate(miles):
        lat, lon = point_at(points, cumulative_mi, mile)
        eta = departure_utc + timedelta(seconds=profile.seconds_at(mile * METERS_PER_MILE))
        owns_from = 0.0 if i == 0 else (miles[i - 1] + mile) / 2
        owns_to = total if i == len(miles) - 1 else (mile + miles[i + 1]) / 2
        checkpoints.append(Checkpoint(i, mile, lat, lon, eta, owns_from, owns_to))
    return checkpoints
