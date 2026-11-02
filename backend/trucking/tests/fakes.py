"""Fake providers and route builders for tests (no network)."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import datetime

from trucking.domain.forecast import HourlySeries
from trucking.domain.geo import METERS_PER_MILE, cumulative_miles
from trucking.domain.types import LatLon, RawRoute
from trucking.services.geocoding.base import GeocodeHit
from trucking.services.routing.base import RoutingError, RoutingResult
from trucking.services.weather.base import WeatherResult, round_point
from trucking.services.weather.open_meteo import floor_hour

CHICAGO: LatLon = (41.8781, -87.6298)
DENVER: LatLon = (39.7392, -104.9903)


def curve(origin: LatLon, dest: LatLon, bulge_deg: float = 0.0, n: int = 400) -> list[LatLon]:
    """A smooth path from origin to dest bulging ``bulge_deg`` degrees of latitude in the middle."""
    pts = []
    for i in range(n):
        t = i / (n - 1)
        pts.append(
            (
                origin[0] + (dest[0] - origin[0]) * t + bulge_deg * math.sin(math.pi * t),
                origin[1] + (dest[1] - origin[1]) * t,
            )
        )
    return pts


def raw_route(
    points: Sequence[LatLon], speed_mph: float = 60.0, guidance: bool = True, via: str | None = None
) -> RawRoute:
    miles = cumulative_miles(points)[-1]
    duration = miles / speed_mph * 3600
    offsets: tuple[tuple[float, float], ...] = ()
    if guidance:
        steps = 12  # slightly non-uniform speed so guidance differs from the uniform fallback
        offsets = tuple(
            (miles * METERS_PER_MILE * (k / steps), duration * ((k / steps) ** 1.1))
            for k in range(steps + 1)
        )
        offsets = (*offsets[:-1], (miles * METERS_PER_MILE, duration))
    return RawRoute(tuple(points), miles * METERS_PER_MILE, duration, offsets, via)


def three_routes(guidance: bool = True) -> list[RawRoute]:
    return [
        raw_route(curve(CHICAGO, DENVER, 0.0), 62, guidance, "I-80 W"),
        raw_route(curve(CHICAGO, DENVER, 1.6), 62, guidance, "I-76 W"),
        raw_route(curve(CHICAGO, DENVER, -1.6), 62, guidance, "I-70 W"),
    ]


class FakeRouting:
    name = "fake-routing"

    def __init__(
        self, routes: Sequence[RawRoute] | None = None, error: RoutingError | None = None
    ) -> None:
        self.routes = tuple(three_routes() if routes is None else routes)
        self.error = error
        self.calls: list[tuple[LatLon, LatLon, datetime]] = []

    def get_routes(
        self, origin: LatLon, destination: LatLon, departure_utc: datetime
    ) -> RoutingResult:
        self.calls.append((origin, destination, departure_utc))
        if self.error:
            raise self.error
        return RoutingResult(self.routes, requested=3)


class FakeWeather:
    """Series built by ``builder(point, start, hours)``; return None to simulate missing data."""

    name = "fake-weather"

    def __init__(self, builder: Callable[[LatLon, datetime, int], HourlySeries | None]) -> None:
        self.builder = builder
        self.calls: list[tuple[int, datetime, datetime]] = []

    def fetch(self, points: Sequence[LatLon], start: datetime, end: datetime) -> WeatherResult:
        start, end = floor_hour(start), floor_hour(end)
        hours = int((end - start).total_seconds() // 3600) + 1
        self.calls.append((len(points), start, end))
        unique = list(dict.fromkeys(round_point(p) for p in points))
        return WeatherResult(series={p: self.builder(p, start, hours) for p in unique})


def constant_weather(wind: float = 10.0, rain: float = 0.0, snow: float = 0.0) -> FakeWeather:
    def build(point: LatLon, start: datetime, hours: int) -> HourlySeries:
        return HourlySeries(
            start,
            (wind,) * hours,
            (wind * 1.3,) * hours,
            (rain,) * hours,
            (snow,) * hours,
            (50.0,) * hours,
            source_units=(("wind", "mp/h"), ("rain", "inch+inch"), ("snow", "inch")),
        )

    return FakeWeather(build)


class FakeGeocoder:
    name = "fake-geocoder"

    def __init__(self, hits: Sequence[GeocodeHit] = ()) -> None:
        self.hits = list(hits)

    def search(self, query: str, limit: int = 6) -> list[GeocodeHit]:
        return self.hits[:limit]
