"""Builders shared by tests (synthetic Open-Meteo responses, fake providers)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from trucking.domain.forecast import HourlySeries

UNITS_IMPERIAL = {
    "time": "iso8601",
    "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
    "temperature_2m": "°F",
}


def om_location(
    hours: int = 6,
    start: datetime = datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
    units: dict[str, str] | None = None,
    **overrides: list[Any],
) -> dict[str, Any]:
    """A synthetic Open-Meteo location object. Defaults: calm, dry, 50 F. Override any variable."""
    hourly: dict[str, list[Any]] = {
        "time": [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)],
        "wind_speed_10m": [10.0] * hours,
        "wind_gusts_10m": [15.0] * hours,
        "rain": [0.0] * hours,
        "showers": [0.0] * hours,
        "snowfall": [0.0] * hours,
        "temperature_2m": [50.0] * hours,
    }
    hourly.update(overrides)
    return {
        "latitude": 41.88,
        "longitude": -87.63,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": units or dict(UNITS_IMPERIAL),
        "hourly": hourly,
    }


def flat_series(
    hours: int = 120,
    start: datetime = datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
    wind: float = 10.0,
    rain: float = 0.0,
    snow: float = 0.0,
) -> HourlySeries:
    return HourlySeries(
        start,
        (wind,) * hours,
        (wind * 1.3,) * hours,
        (rain,) * hours,
        (snow,) * hours,
        (50.0,) * hours,
        source_units=(("wind", "mp/h"), ("rain", "inch+inch"), ("snow", "inch")),
    )
