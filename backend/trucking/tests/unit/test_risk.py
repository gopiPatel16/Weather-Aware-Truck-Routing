"""Risk engine: every exact boundary, just-below / just-above, load rules, Unknown handling."""

import math

import pytest

from trucking.domain.risk import assess_risk
from trucking.domain.types import RiskLevel

L, M, H, S, N = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
LIGHT = 1_000  # a load that triggers no load rule


def below(x: float) -> float:
    return math.nextafter(x, -math.inf)


def above(x: float) -> float:
    return math.nextafter(x, math.inf)


WIND_CASES = [
    (0, L),
    (below(25), L),
    (25, M),
    (30, M),
    (below(35), M),
    (35, H),
    (below(45), H),
    (45, S),
    (below(55), S),
    (55, N),
    (above(55), N),
    (90, N),
]
RAIN_CASES = [
    (0, L),
    (below(0.10), L),
    (0.10, M),
    (below(0.25), M),
    (0.25, H),
    (below(0.50), H),
    (0.50, S),
    (0.75, S),
    (1.00, S),
    (above(1.00), N),
    (2.5, N),
]
SNOW_CASES = [
    (0, L),
    (below(0.5), L),
    (0.5, M),
    (below(1.0), M),
    (1.0, H),
    (below(2.0), H),
    (2.0, S),
    (2.5, S),
    (3.0, S),
    (above(3.0), N),
    (6, N),
]


@pytest.mark.parametrize(("wind", "expected"), WIND_CASES)
def test_wind_bands(wind, expected):
    assert assess_risk(wind, 0, 0, LIGHT).level == expected


@pytest.mark.parametrize(("rain", "expected"), RAIN_CASES)
def test_rain_bands(rain, expected):
    assert assess_risk(0, rain, 0, LIGHT).level == expected


@pytest.mark.parametrize(("snow", "expected"), SNOW_CASES)
def test_snow_bands(snow, expected):
    assert assess_risk(0, 0, snow, LIGHT).level == expected


def test_final_level_is_most_severe_of_conditions():
    assert assess_risk(30, 0.30, 0, LIGHT).level == H  # Moderate wind + High rain
    assert assess_risk(10, 0.05, 2.5, LIGHT).level == S


@pytest.mark.parametrize(
    ("wind", "cargo", "expected"),
    [
        (55, 1, N),  # any load
        (60, 0.0, N),
        (45, 30_000, S),  # 30,000 is NOT over 30,000
        (45, 30_001, N),
        (below(55), 30_000, S),
        (below(55), 30_001, N),
        (44.9, 100_000, S),  # 35-44 rule, not the 45-54 rule
        (35, 40_000, H),  # 40,000 is NOT over 40,000
        (35, 40_001, S),
        (below(45), 40_001, S),
        (34.9, 100_000, M),  # below 35: no load rule
        (50, 25_000, S),
    ],
)
def test_load_rules(wind, cargo, expected):
    assert assess_risk(wind, 0, 0, cargo).level == expected


def test_load_rule_never_lowers_a_higher_level():
    assert assess_risk(40, 0, 2.5, 50_000).level == S
    assert assess_risk(40, 0, 3.5, 50_000).level == N


def test_load_rule_driver_is_reported():
    result = assess_risk(40, 0, 0, 42_000)
    assert result.level == S
    assert any(d.factor == "load_rule" for d in result.drivers)
    assert any(d.factor == "wind" and d.level == H for d in result.drivers)


def test_low_conditions_have_no_drivers():
    assert assess_risk(10, 0.01, 0, 80_000).drivers == ()


# ---- Unknown is never Low ----------------------------------------------------------------
def test_all_missing_is_unknown():
    r = assess_risk(None, None, None, LIGHT)
    assert r.level is None and set(r.missing) == {"wind", "rain", "snow"} and r.at_least is None


def test_missing_one_input_is_unknown_not_low():
    r = assess_risk(10, 0, None, LIGHT)
    assert r.level is None and r.missing == ("snow",) and r.at_least == L


def test_unknown_reports_lower_bound_from_known_inputs():
    r = assess_risk(None, 0.8, 0, LIGHT)
    assert r.level is None and r.at_least == S


def test_missing_input_but_known_no_travel_is_no_travel():
    assert assess_risk(60, None, None, LIGHT).level == N
    assert assess_risk(None, 1.5, None, LIGHT).level == N
    assert assess_risk(50, None, None, 35_000).level == N  # load rule proves No Travel


@pytest.mark.parametrize("bad", [math.nan, math.inf, -1.0])
def test_invalid_readings_count_as_missing(bad):
    assert assess_risk(bad, 0, 0, LIGHT).level is None
    assert assess_risk(0, bad, 0, LIGHT).level is None
    assert assess_risk(0, 0, bad, LIGHT).level is None
