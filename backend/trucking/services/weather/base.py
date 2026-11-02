"""Weather provider contract and a tiny cache protocol (so services never import Django)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from trucking.config import WEATHER_COORD_DECIMALS
from trucking.domain.forecast import HourlySeries
from trucking.domain.types import LatLon


def round_point(point: LatLon) -> LatLon:
    """Weather queries and cache keys use ~1 km resolution - finer than the forecast models' grids."""
    return (round(point[0], WEATHER_COORD_DECIMALS), round(point[1], WEATHER_COORD_DECIMALS))


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_s: int) -> None: ...


class WeatherError(Exception):
    """Base class for weather failures."""


class WeatherUnavailable(WeatherError):
    """Provider unreachable, rate-limited or erroring after retries."""

    def __init__(self, message: str, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class WeatherFormatError(WeatherError, ValueError):
    """The provider's response did not have the expected shape or units."""


@dataclass
class WeatherResult:
    """Series keyed by the ROUNDED query point. ``None`` = no data (the checkpoint becomes Unknown)."""

    series: dict[LatLon, HourlySeries | None]
    cache_hits: int = 0
    cache_misses: int = 0
    failed_points: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def all_failed(self) -> bool:
        return bool(self.series) and all(s is None for s in self.series.values())


class WeatherProvider(Protocol):
    name: str

    def fetch(self, points: Sequence[LatLon], start: datetime, end: datetime) -> WeatherResult:
        """Hourly forecast covering [start, end] (UTC, hour-aligned) for every point."""
        ...
