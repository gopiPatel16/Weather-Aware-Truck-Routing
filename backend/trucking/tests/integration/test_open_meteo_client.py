"""Open-Meteo client with mocked HTTP: batching, cache, retries, clamping, partial failure."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from trucking.domain.forecast import assess_selection, select_forecast
from trucking.domain.types import RiskLevel
from trucking.services.weather.base import round_point
from trucking.services.weather.cache import DictCache
from trucking.services.weather.mock import MockWeatherProvider
from trucking.services.weather.open_meteo import FREE_URL, PAID_URL, OpenMeteoClient
from trucking.tests.helpers import om_location

NOW = datetime(2026, 11, 1, 12, 30, tzinfo=UTC)
START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=5)


def client(**kwargs):
    sleeps: list[float] = []
    c = OpenMeteoClient(
        cache=kwargs.pop("cache", DictCache()),
        http=httpx.Client(),
        sleep=sleeps.append,
        clock=lambda: NOW,
        **kwargs,
    )
    return c, sleeps


def locations(n: int):
    return [om_location(6) for _ in range(n)]


@respx.mock
def test_multi_point_request_parameters_and_order():
    route = respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=locations(2)))
    c, _ = client()
    result = c.fetch([(41.8781, -87.6298), (39.7392, -104.9903)], START, END)
    params = dict(route.calls[0].request.url.params)
    assert params["latitude"] == "41.88,39.74" and params["longitude"] == "-87.63,-104.99"
    assert (
        params["wind_speed_unit"],
        params["precipitation_unit"],
        params["temperature_unit"],
        params["timezone"],
    ) == ("mph", "inch", "fahrenheit", "GMT")
    assert params["start_hour"] == "2026-11-02T12:00" and params["end_hour"] == "2026-11-02T17:00"
    assert set(result.series) == {(41.88, -87.63), (39.74, -104.99)}
    assert all(s is not None for s in result.series.values()) and result.cache_misses == 2


@respx.mock
def test_single_location_response_is_a_dict_not_a_list():
    respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=om_location(6)))
    c, _ = client()
    result = c.fetch([(41.88, -87.63)], START, END)
    assert result.series[(41.88, -87.63)] is not None


@respx.mock
def test_results_are_cached_and_not_refetched():
    route = respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=locations(1)))
    c, _ = client()
    c.fetch([(41.88, -87.63)], START, END)
    second = c.fetch([(41.881, -87.629)], START, END)  # rounds to the same 0.01 degree point
    assert route.call_count == 1 and second.cache_hits == 1 and second.cache_misses == 0


@respx.mock
def test_different_windows_do_not_share_cache_entries():
    route = respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=locations(1)))
    c, _ = client()
    c.fetch([(41.88, -87.63)], START, END)
    c.fetch([(41.88, -87.63)], START, END + timedelta(hours=2))
    assert route.call_count == 2


@respx.mock
def test_requests_are_chunked():
    route = respx.get(FREE_URL).mock(
        side_effect=lambda request: httpx.Response(
            200, json=locations(len(request.url.params["latitude"].split(",")))
        )
    )
    c, _ = client(chunk_size=2, max_workers=2)
    result = c.fetch([(40.0 + i, -100.0) for i in range(5)], START, END)
    assert route.call_count == 3 and len(result.series) == 5 and result.failed_points == 0


@respx.mock
def test_rate_limit_is_retried_with_backoff_then_succeeds():
    respx.get(FREE_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json=locations(1)),
        ]
    )
    c, sleeps = client()
    result = c.fetch([(41.88, -87.63)], START, END)
    assert result.series[(41.88, -87.63)] is not None and sleeps == [2.0]


@respx.mock
def test_persistent_server_errors_make_points_unknown_and_warn():
    respx.get(FREE_URL).mock(return_value=httpx.Response(503))
    c, sleeps = client()
    result = c.fetch([(41.88, -87.63), (40.0, -100.0)], START, END)
    assert result.all_failed and result.failed_points == 2 and len(sleeps) == 2
    assert result.warnings and "unavailable" in result.warnings[0]


@respx.mock
def test_timeout_is_retried():
    respx.get(FREE_URL).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json=locations(1))]
    )
    c, sleeps = client()
    assert (
        c.fetch([(41.88, -87.63)], START, END).series[(41.88, -87.63)] is not None
        and len(sleeps) == 1
    )


@respx.mock
def test_out_of_range_400_is_not_retried():
    route = respx.get(FREE_URL).mock(
        return_value=httpx.Response(400, json={"error": True, "reason": "out of allowed range"})
    )
    c, sleeps = client()
    result = c.fetch([(41.88, -87.63)], START, END)
    assert route.call_count == 1 and not sleeps and result.failed_points == 1


@respx.mock
def test_invalid_json_and_wrong_location_count_are_failures():
    respx.get(FREE_URL).mock(
        side_effect=[httpx.Response(200, text="<html>"), httpx.Response(200, json=locations(1))]
    )
    c, _ = client()
    assert c.fetch([(41.88, -87.63)], START, END).failed_points == 1
    c2, _ = client()
    result = c2.fetch(
        [(41.88, -87.63), (40.0, -100.0)], START, END
    )  # provider returned 1 for 2 points
    assert result.failed_points == 2


@respx.mock
def test_one_unusable_location_does_not_poison_the_others():
    bad = om_location(6, units={**om_location(1)["hourly_units"], "snowfall": "furlongs"})
    respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=[om_location(6), bad]))
    c, _ = client()
    result = c.fetch([(41.88, -87.63), (40.0, -100.0)], START, END)
    assert result.series[(41.88, -87.63)] is not None and result.series[(40.0, -100.0)] is None
    assert result.failed_points == 1 and "unusable" in result.warnings[0] and not result.all_failed


@respx.mock
def test_end_is_clamped_to_the_forecast_horizon():
    route = respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=locations(1)))
    c, _ = client()
    c.fetch(
        [(41.88, -87.63)],
        datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 0, 0, tzinfo=UTC),
    )
    assert route.calls[0].request.url.params["end_hour"] == "2026-11-16T00:00"  # today + 15 days


@respx.mock
def test_window_entirely_beyond_horizon_makes_everything_unknown_without_a_request():
    route = respx.get(FREE_URL).mock(return_value=httpx.Response(200, json=locations(1)))
    c, _ = client()
    result = c.fetch(
        [(41.88, -87.63)],
        datetime(2026, 12, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 12, 3, 0, 0, tzinfo=UTC),
    )
    assert route.call_count == 0 and result.all_failed and "horizon" in result.warnings[0]


@respx.mock
def test_paid_key_uses_customer_endpoint():
    route = respx.get(PAID_URL).mock(return_value=httpx.Response(200, json=locations(1)))
    c, _ = client(api_key="secret")
    c.fetch([(41.88, -87.63)], START, END)
    assert route.calls[0].request.url.params["apikey"] == "secret"


def test_round_point():
    assert round_point((41.8781, -87.6298)) == (41.88, -87.63)


# ---- mock provider ------------------------------------------------------------------------
def test_mock_calm_is_all_low():
    result = MockWeatherProvider("calm").fetch([(41.88, -87.63)], START, END)
    series = result.series[(41.88, -87.63)]
    assert (
        assess_selection(select_forecast(series, START + timedelta(hours=2)), 50_000)[0].level
        == RiskLevel.LOW
    )


def test_mock_storm_reaches_no_travel_and_moves_east():
    provider = MockWeatherProvider("plains_storm")
    point = (42.0, -100.0)
    series = provider.fetch([point], START, START + timedelta(hours=40)).series[point]
    levels = [
        assess_selection(select_forecast(series, START + timedelta(hours=h)), 50_000)[0].level
        for h in range(40)
    ]
    assert (
        RiskLevel.NO_TRAVEL in levels and levels[0] == RiskLevel.LOW and levels[-1] == RiskLevel.LOW
    )


def test_mock_rejects_unknown_scenario():
    with pytest.raises(ValueError):
        MockWeatherProvider("tornado")


@respx.mock
def test_minutely_limit_waits_for_the_next_minute_then_succeeds():
    respx.get(FREE_URL).mock(
        side_effect=[
            httpx.Response(
                429, json={"error": True, "reason": "Minutely API request limit exceeded."}
            ),
            httpx.Response(200, json=locations(1)),
        ]
    )
    c, sleeps = client()
    result = c.fetch([(41.88, -87.63)], START, END)
    assert result.series[(41.88, -87.63)] is not None and sleeps == [20.0]


@respx.mock
def test_hourly_limit_fails_fast_without_waiting():
    route = respx.get(FREE_URL).mock(
        return_value=httpx.Response(
            429, json={"error": True, "reason": "Hourly API request limit exceeded."}
        )
    )
    c, sleeps = client()
    result = c.fetch([(41.88, -87.63)], START, END)
    assert result.all_failed and route.call_count == 1 and sleeps == []
    assert "429" in result.warnings[0]


@respx.mock
def test_minutely_limit_gives_up_after_three_waits():
    respx.get(FREE_URL).mock(
        return_value=httpx.Response(
            429, json={"error": True, "reason": "Minutely API request limit exceeded."}
        )
    )
    c, sleeps = client()
    result = c.fetch([(41.88, -87.63)], START, END)
    assert result.all_failed and sleeps[:3] == [20.0] * 3
