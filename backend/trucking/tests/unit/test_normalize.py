"""Unit normalisation and the Open-Meteo response guard."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trucking.domain.risk import assess_risk
from trucking.domain.types import RiskLevel
from trucking.services.weather.base import WeatherFormatError
from trucking.services.weather.normalize import normalize_location
from trucking.tests.helpers import om_location

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "open_meteo_multi_point.json"


def test_real_spike_response_normalises():
    locations = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(locations) == 3
    for location in locations:
        series = normalize_location(location)
        assert len(series) == 51 and series.start.tzinfo is UTC
        assert dict(series.source_units)["wind"] == "mp/h"  # NOT the string "mph"
        assert dict(series.source_units)["snow"] == "inch"
        assert all(v is not None for v in series.wind_mph)


def test_rain_is_rain_plus_showers():
    series = normalize_location(om_location(2, rain=[0.10, 0.0], showers=[0.05, 0.2]))
    assert series.rain_in == pytest.approx((0.15, 0.2))


def test_metric_units_are_converted_not_compared_raw():
    metric_units = {
        "time": "iso8601",
        "wind_speed_10m": "km/h",
        "wind_gusts_10m": "km/h",
        "rain": "mm",
        "showers": "mm",
        "snowfall": "cm",
        "temperature_2m": "°C",
    }
    series = normalize_location(
        om_location(
            2,
            units=metric_units,
            wind_speed_10m=[100.0, 0.0],
            wind_gusts_10m=[160.9344, 0.0],
            rain=[25.4, 0.0],
            showers=[0.0, 0.0],
            snowfall=[2.54, 5.08],
            temperature_2m=[0.0, 100.0],
        )
    )
    assert series.wind_mph[0] == pytest.approx(62.1371, abs=1e-3)
    assert series.gust_mph[0] == pytest.approx(100.0, abs=1e-2)
    assert series.rain_in[0] == pytest.approx(1.0)
    assert series.snow_in == pytest.approx((1.0, 2.0))
    assert series.temp_f == pytest.approx((32.0, 212.0))


def test_other_wind_units():
    for unit, value, expected in (("m/s", 10.0, 22.369), ("kn", 10.0, 11.508)):
        units = {
            "time": "iso8601",
            "wind_speed_10m": unit,
            "wind_gusts_10m": unit,
            "rain": "inch",
            "showers": "inch",
            "snowfall": "inch",
            "temperature_2m": "°F",
        }
        series = normalize_location(
            om_location(1, units=units, wind_speed_10m=[value], wind_gusts_10m=[value])
        )
        assert series.wind_mph[0] == pytest.approx(expected, abs=1e-2)


def test_snowfall_unit_is_inspected_not_assumed_from_precipitation_unit():
    # inch rain/showers but snowfall still in cm: converted using the snowfall unit itself
    units = {
        "time": "iso8601",
        "wind_speed_10m": "mp/h",
        "wind_gusts_10m": "mp/h",
        "rain": "inch",
        "showers": "inch",
        "snowfall": "cm",
        "temperature_2m": "°F",
    }
    series = normalize_location(om_location(1, units=units, snowfall=[7.62]))
    assert series.snow_in[0] == pytest.approx(3.0)


@pytest.mark.parametrize(
    "variable",
    ["wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m"],
)
def test_unrecognised_unit_raises_instead_of_guessing(variable):
    units = {
        "time": "iso8601",
        "wind_speed_10m": "mp/h",
        "wind_gusts_10m": "mp/h",
        "rain": "inch",
        "showers": "inch",
        "snowfall": "inch",
        "temperature_2m": "°F",
    }
    units[variable] = "furlongs"
    with pytest.raises(WeatherFormatError, match="unrecognised unit"):
        normalize_location(om_location(1, units=units))


def test_converted_values_meet_the_thresholds_exactly():
    # 6.35 mm is exactly 0.25 in: the High boundary. Float noise must not flip it to Moderate.
    metric = {
        "time": "iso8601",
        "wind_speed_10m": "mp/h",
        "wind_gusts_10m": "mp/h",
        "rain": "mm",
        "showers": "mm",
        "snowfall": "cm",
        "temperature_2m": "°F",
    }
    series = normalize_location(
        om_location(2, units=metric, rain=[6.35, 25.4], snowfall=[7.62, 7.6201])
    )
    assert assess_risk(0, series.rain_in[0], 0, 1000).level == RiskLevel.HIGH
    assert assess_risk(0, series.rain_in[1], 0, 1000).level == RiskLevel.SEVERE  # exactly 1.00 in
    assert assess_risk(0, 0, series.snow_in[0], 1000).level == RiskLevel.SEVERE  # exactly 3.0 in
    assert assess_risk(0, 0, series.snow_in[1], 1000).level == RiskLevel.NO_TRAVEL


def test_nulls_stay_missing_never_zero():
    series = normalize_location(
        om_location(
            3, wind_speed_10m=[5.0, None, 5.0], showers=[0.0, 0.0, None], snowfall=[None, 0.0, 0.0]
        )
    )
    assert series.wind_mph[1] is None
    assert series.rain_in[2] is None  # showers missing -> rain unknown
    assert series.snow_in[0] is None


def test_missing_variable_raises():
    location = om_location(2)
    del location["hourly"]["showers"]
    with pytest.raises(WeatherFormatError, match="missing variables"):
        normalize_location(location)


def test_length_mismatch_raises():
    with pytest.raises(WeatherFormatError, match="expected 2"):
        normalize_location(om_location(2, rain=[0.0]))


def test_timestamps_must_be_consecutive_hours_and_parseable():
    location = om_location(3)
    location["hourly"]["time"][2] = "2026-11-02T20:00"
    with pytest.raises(WeatherFormatError, match="consecutive"):
        normalize_location(location)
    location["hourly"]["time"] = ["yesterday"] * 3
    with pytest.raises(WeatherFormatError, match="timestamp"):
        normalize_location(location)


def test_non_gmt_response_is_rejected():
    location = om_location(2)
    location["utc_offset_seconds"] = -21600
    with pytest.raises(WeatherFormatError, match="timezone=GMT"):
        normalize_location(location)


def test_response_without_hourly_data_raises():
    with pytest.raises(WeatherFormatError):
        normalize_location({"latitude": 1, "longitude": 2})


def test_first_stamp_is_preserved():
    series = normalize_location(om_location(2, start=datetime(2026, 11, 3, 5, 0, tzinfo=UTC)))
    assert series.start == datetime(2026, 11, 3, 5, 0, tzinfo=UTC)
