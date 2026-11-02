"""ETA -> forecast interval matching policy (plan 5.4)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from trucking.domain.forecast import HourlySeries, assess_selection, select_forecast
from trucking.domain.types import RiskLevel

START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def make_series(n=10, wind=None, rain=None, snow=None) -> HourlySeries:
    """Hour i has stamp START + i h. Defaults: calm and dry. Overrides are {hour_index: value}."""

    def build(default, overrides):
        values = [default] * n
        for k, v in (overrides or {}).items():
            values[k] = v
        return tuple(values)

    return HourlySeries(
        START,
        build(10.0, wind),
        build(15.0, None),
        build(0.0, rain),
        build(0.0, snow),
        build(50.0, None),
    )


def at(minutes_after_14: int) -> datetime:
    return datetime(2026, 11, 2, 14, 0, tzinfo=UTC) + timedelta(minutes=minutes_after_14)


def test_mid_hour_uses_covering_interval_only():
    sel = select_forecast(make_series(), at(20))
    assert len(sel.candidates) == 1
    c = sel.candidates[0]
    assert (c.interval_start, c.interval_end) == (at(0), at(60))  # record stamped 15:00
    assert sel.wind_stamps == (at(0), at(60))
    assert not sel.adjacent_interval_used


def test_wind_is_linearly_interpolated():
    series = make_series(wind={2: 20.0, 3: 40.0})  # stamps 14:00 and 15:00
    assert select_forecast(series, at(0)).wind_mph == pytest.approx(20.0)
    assert select_forecast(series, at(30)).wind_mph == pytest.approx(30.0)
    assert select_forecast(series, at(45)).wind_mph == pytest.approx(35.0)


def test_exactly_on_the_hour_checks_previous_interval_too():
    sel = select_forecast(make_series(), at(0))
    assert [c.interval_end for c in sel.candidates] == [at(60), at(0)]  # covering, then previous
    assert sel.adjacent_interval_used


@pytest.mark.parametrize(
    ("minute", "adjacent"),
    [(0, True), (14, True), (15, False), (44, False), (45, True), (59, True)],
)
def test_adjacency_margin_is_fifteen_minutes(minute, adjacent):
    assert select_forecast(make_series(), at(minute)).adjacent_interval_used is adjacent


def test_late_in_hour_checks_next_interval():
    sel = select_forecast(make_series(), at(50))
    assert [c.interval_end for c in sel.candidates] == [at(60), at(120)]


def test_precipitation_uses_preceding_hour_record_not_nearest():
    # 14:20 -> interval [14:00,15:00) -> record stamped 15:00 (index 3). A "nearest hour" shortcut
    # would have picked 14:00 (index 2).
    series = make_series(rain={2: 0.9, 3: 0.0})
    sel = select_forecast(series, at(20))
    assert sel.candidates[0].rain_in == 0.0
    assert assess_selection(sel, 1000)[0].level == RiskLevel.LOW
    series = make_series(rain={2: 0.0, 3: 0.9})
    assert assess_selection(select_forecast(series, at(20)), 1000)[0].level == RiskLevel.SEVERE


def test_adjacent_interval_can_only_raise_risk():
    series = make_series(rain={2: 0.6, 3: 0.0})  # previous interval (stamp 14:00) is Severe
    assert assess_selection(select_forecast(series, at(5)), 1000)[0].level == RiskLevel.SEVERE
    assert assess_selection(select_forecast(series, at(20)), 1000)[0].level == RiskLevel.LOW


def test_no_travel_in_adjacent_interval_wins():
    series = make_series(snow={4: 4.0})  # stamp 16:00, next interval when ETA is 14:50
    assert assess_selection(select_forecast(series, at(50)), 1000)[0].level == RiskLevel.NO_TRAVEL


def test_worst_candidate_values_are_reported():
    series = make_series(rain={2: 0.3, 3: 0.1})
    assessment, candidate = assess_selection(select_forecast(series, at(5)), 1000)
    assert assessment.level == RiskLevel.HIGH and candidate.rain_in == 0.3


def test_missing_covering_value_is_unknown_even_if_neighbour_is_known():
    series = make_series(rain={3: None})
    assessment, _ = assess_selection(select_forecast(series, at(5)), 1000)
    assert assessment.level is None and assessment.missing == ("rain",)


def test_missing_adjacent_value_is_ignored():
    series = make_series(rain={2: None})  # previous interval missing, covering known
    assessment, _ = assess_selection(select_forecast(series, at(5)), 1000)
    assert assessment.level == RiskLevel.LOW


def test_unknown_covering_reports_lower_bound_from_neighbour():
    series = make_series(rain={3: None, 2: 0.6})
    assessment, _ = assess_selection(select_forecast(series, at(5)), 1000)
    assert assessment.level is None and assessment.at_least == RiskLevel.SEVERE


def test_time_outside_series_is_unknown_not_low():
    series = make_series(n=4)  # stamps 12:00..15:00
    sel = select_forecast(series, at(200))  # 17:20
    assert sel.wind_mph is None
    assert assess_selection(sel, 1000)[0].level is None


def test_wind_missing_at_a_bracketing_stamp_is_unknown():
    series = make_series(wind={3: None})
    assert select_forecast(series, at(30)).wind_mph is None
    assert select_forecast(series, at(0)).wind_mph == 10.0  # f == 0 only needs the earlier stamp


def test_aware_non_utc_times_are_normalised():
    central = timezone(timedelta(hours=-6))
    local = datetime(2026, 11, 2, 8, 20, tzinfo=central)  # == 14:20 UTC
    assert select_forecast(make_series(), local).candidates[0].interval_end == at(60)


def test_series_validation():
    with pytest.raises(ValueError):
        HourlySeries(
            datetime(2026, 11, 2, 12, 30, tzinfo=UTC), (1.0,), (1.0,), (1.0,), (1.0,), (1.0,)
        )
    with pytest.raises(ValueError):
        HourlySeries(START, (1.0, 2.0), (1.0,), (1.0,), (1.0,), (1.0,))
