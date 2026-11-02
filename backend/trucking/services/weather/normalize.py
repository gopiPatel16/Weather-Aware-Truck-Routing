"""Normalise one Open-Meteo location into an ``HourlySeries`` (mph, inches in the hour, deg F).

Units are read from the response's ``hourly_units`` every time and converted with a CLOSED table.
An unrecognised unit string raises - nothing is ever guessed. Notably Open-Meteo reports mph as
``"mp/h"`` and snowfall in inches only when ``precipitation_unit=inch`` was requested; neither is
assumed here, both are checked per response.

Rain is ``rain + showers``: large-scale rain and convective showers are reported separately, both
fall as liquid on the road, and the brief's rain thresholds concern liquid rainfall rate.
``precipitation`` is not used because it also contains snow water-equivalent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from trucking.domain.forecast import HourlySeries

from .base import WeatherFormatError

HOURLY_VARIABLES = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "temperature_2m",
)

WIND_FACTORS = {"mp/h": 1.0, "mph": 1.0, "km/h": 0.621371192, "m/s": 2.236936292, "kn": 1.150779448}
RAIN_FACTORS = {"inch": 1.0, "mm": 1 / 25.4}
SNOW_FACTORS = {"inch": 1.0, "cm": 1 / 2.54}
TEMPERATURE_CONVERTERS: dict[str, Callable[[float], float]] = {
    "°F": lambda v: v,
    "°C": lambda v: v * 9 / 5 + 32,
}

TIME_FORMAT = "%Y-%m-%dT%H:%M"
_ROUND = 6  # removes float noise before values meet the thresholds


def _factor(table: Mapping[str, float], unit: object, variable: str) -> float:
    if not isinstance(unit, str) or unit not in table:
        raise WeatherFormatError(f"unrecognised unit {unit!r} for {variable}")
    return table[unit]


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _convert(values: Sequence[object], fn: Callable[[float], float]) -> list[float | None]:
    out: list[float | None] = []
    for raw in values:
        number = _number(raw)
        out.append(None if number is None else round(fn(number), _ROUND))
    return out


def parse_times(times: Sequence[object]) -> list[datetime]:
    try:
        stamps = [datetime.strptime(str(t), TIME_FORMAT).replace(tzinfo=UTC) for t in times]
    except ValueError as exc:
        raise WeatherFormatError(f"bad timestamp format: {exc}") from exc
    if not stamps:
        raise WeatherFormatError("empty hourly series")
    if any(b - a != timedelta(hours=1) for a, b in zip(stamps, stamps[1:], strict=False)):
        raise WeatherFormatError("hourly timestamps are not consecutive hours")
    return stamps


def normalize_location(location: Mapping[str, Any]) -> HourlySeries:
    hourly = location.get("hourly")
    units = location.get("hourly_units")
    if not isinstance(hourly, Mapping) or not isinstance(units, Mapping):
        raise WeatherFormatError("response has no hourly data or hourly_units")
    if location.get("utc_offset_seconds", 0) != 0:
        raise WeatherFormatError("expected timezone=GMT (utc_offset_seconds must be 0)")
    missing = [v for v in ("time", *HOURLY_VARIABLES) if v not in hourly]
    if missing:
        raise WeatherFormatError(f"missing variables: {', '.join(missing)}")

    stamps = parse_times(hourly["time"])
    n = len(stamps)
    for variable in HOURLY_VARIABLES:
        if len(hourly[variable]) != n:
            raise WeatherFormatError(f"{variable} has {len(hourly[variable])} values, expected {n}")

    wind_f = _factor(WIND_FACTORS, units.get("wind_speed_10m"), "wind_speed_10m")
    gust_f = _factor(WIND_FACTORS, units.get("wind_gusts_10m"), "wind_gusts_10m")
    rain_f = _factor(RAIN_FACTORS, units.get("rain"), "rain")
    showers_f = _factor(RAIN_FACTORS, units.get("showers"), "showers")
    snow_f = _factor(SNOW_FACTORS, units.get("snowfall"), "snowfall")
    temp_unit = units.get("temperature_2m")
    if temp_unit not in TEMPERATURE_CONVERTERS:
        raise WeatherFormatError(f"unrecognised unit {temp_unit!r} for temperature_2m")

    rain = _convert(hourly["rain"], lambda v: v * rain_f)
    showers = _convert(hourly["showers"], lambda v: v * showers_f)
    rain_total = [
        None if a is None or b is None else round(a + b, _ROUND)
        for a, b in zip(rain, showers, strict=True)
    ]

    return HourlySeries(
        start=stamps[0],
        wind_mph=tuple(_convert(hourly["wind_speed_10m"], lambda v: v * wind_f)),
        gust_mph=tuple(_convert(hourly["wind_gusts_10m"], lambda v: v * gust_f)),
        rain_in=tuple(rain_total),
        snow_in=tuple(_convert(hourly["snowfall"], lambda v: v * snow_f)),
        temp_f=tuple(_convert(hourly["temperature_2m"], TEMPERATURE_CONVERTERS[temp_unit])),
        source_units=(
            ("wind", str(units["wind_speed_10m"])),
            ("rain", f"{units['rain']}+{units['showers']}"),
            ("snow", str(units["snowfall"])),
        ),
    )
