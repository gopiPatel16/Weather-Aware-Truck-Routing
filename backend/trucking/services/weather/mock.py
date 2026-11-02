"""Deterministic weather for tests and demos (``WEATHER_PROVIDER=mock``).

Real forecasts are often calm, which makes Severe / No Travel behaviour hard to demonstrate. The
mock produces a synthetic, clearly labelled storm so the full pipeline can be shown on any day.
The UI shows a DEMO WEATHER badge whenever this provider is active.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from trucking.domain.forecast import HourlySeries
from trucking.domain.types import LatLon

from .base import WeatherResult, round_point
from .open_meteo import floor_hour

SCENARIOS = ("calm", "plains_storm")


class MockWeatherProvider:
    name = "mock"

    def __init__(self, scenario: str = "plains_storm") -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; choose from {SCENARIOS}")
        self.scenario = scenario

    def fetch(self, points: Sequence[LatLon], start: datetime, end: datetime) -> WeatherResult:
        start, end = floor_hour(start), floor_hour(end)
        hours = int((end - start) / timedelta(hours=1)) + 1
        unique = list(dict.fromkeys(round_point(p) for p in points))
        return WeatherResult(series={p: self._series(p, start, hours) for p in unique})

    def _series(self, point: LatLon, start: datetime, hours: int) -> HourlySeries:
        wind, gust, rain, snow, temp = [], [], [], [], []
        for h in range(hours):
            w, r, s = self._conditions(point, h)
            wind.append(round(w, 2))
            gust.append(round(w * 1.3, 2))
            rain.append(round(r, 3))
            snow.append(round(s, 3))
            temp.append(28.0 if s > 0 else 55.0)
        return HourlySeries(
            start,
            tuple(wind),
            tuple(gust),
            tuple(rain),
            tuple(snow),
            tuple(temp),
            source_units=(("wind", "mp/h"), ("rain", "inch+inch"), ("snow", "inch")),
        )

    def _conditions(self, point: LatLon, hour: int) -> tuple[float, float, float]:
        """(wind mph, rain in/hr, snow in/hr). 'plains_storm': a front moving east at ~0.9 deg/hour."""
        base_wind = 12.0
        if self.scenario == "calm":
            return base_wind, 0.0, 0.0
        lat, lon = point
        centre = -112.0 + 0.9 * hour
        across = max(0.0, 1.0 - abs(lon - centre) / 3.0)
        band = max(0.0, 1.0 - abs(lat - 42.0) / 7.0)
        s = across * band
        wind = base_wind + 46.0 * s
        snow = 3.4 * s if s > 0.25 else 0.0
        rain = 0.0 if snow else 0.6 * s
        return wind, rain, snow
