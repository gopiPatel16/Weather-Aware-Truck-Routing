"""Risk engine: the assignment's wind / rain / snow thresholds and cargo-weight load rules.

Boundary convention (plan 5.6, from the review document section 3):
  * Low is below the first threshold.
  * Every later band INCLUDES its lower bound and EXCLUDES its upper bound.
  * No Travel for rain and snow begins strictly ABOVE the printed Severe upper bound
    (so exactly 1.00 in/hr and exactly 3.0 in/hr are Severe). Wind No Travel is printed ">= 55".

Missing inputs never become zero or Low: see ``assess_risk``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .types import Driver, RiskAssessment, RiskLevel


@dataclass(frozen=True)
class Bands:
    """Lower bounds of the Moderate / High / Severe bands and the No Travel threshold."""

    moderate: float
    high: float
    severe: float
    no_travel: float
    no_travel_inclusive: bool  # True: value >= no_travel; False: value > no_travel


WIND_MPH = Bands(25, 35, 45, 55, no_travel_inclusive=True)
RAIN_IN_HR = Bands(0.10, 0.25, 0.50, 1.00, no_travel_inclusive=False)
SNOW_IN_HR = Bands(0.5, 1.0, 2.0, 3.0, no_travel_inclusive=False)


@dataclass(frozen=True)
class LoadRule:
    """Applies when wind is in [wind_min, wind_max) and cargo weight is strictly over cargo_over_lb."""

    wind_min: float
    wind_max: float | None
    cargo_over_lb: float | None  # None = any load
    result: RiskLevel
    text: str


LOAD_RULES: tuple[LoadRule, ...] = (
    LoadRule(
        55, None, None, RiskLevel.NO_TRAVEL, "wind of 55 mph or more is No Travel for any load"
    ),
    LoadRule(
        45, 55, 30_000, RiskLevel.NO_TRAVEL, "45–54 mph wind with cargo over 30,000 lb is No Travel"
    ),
    LoadRule(
        35, 45, 40_000, RiskLevel.SEVERE, "35–44 mph wind with cargo over 40,000 lb is Severe"
    ),
)


def classify(value: float, bands: Bands) -> RiskLevel:
    """Base level of one weather quantity."""
    over = value >= bands.no_travel if bands.no_travel_inclusive else value > bands.no_travel
    if over:
        return RiskLevel.NO_TRAVEL
    if value >= bands.severe:
        return RiskLevel.SEVERE
    if value >= bands.high:
        return RiskLevel.HIGH
    if value >= bands.moderate:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def load_floor(wind_mph: float, cargo_lb: float) -> tuple[RiskLevel, str] | None:
    """The most severe load rule that applies, if any (applied as a floor, never lowers a level)."""
    best: tuple[RiskLevel, str] | None = None
    for rule in LOAD_RULES:
        in_wind = wind_mph >= rule.wind_min and (rule.wind_max is None or wind_mph < rule.wind_max)
        heavy = rule.cargo_over_lb is None or cargo_lb > rule.cargo_over_lb
        if in_wind and heavy and (best is None or rule.result > best[0]):
            best = (rule.result, rule.text)
    return best


def _clean(value: float | None) -> float | None:
    """Missing, NaN, infinite or negative readings are treated as missing - never as zero."""
    if value is None or not math.isfinite(value) or value < 0:
        return None
    return value


def assess_risk(
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    cargo_lb: float,
) -> RiskAssessment:
    """Risk for one set of normalised readings and the cargo weight in pounds.

    ``level = max(wind, rain, snow, load-rule floor)``. If a reading is missing the result is
    Unknown (``level=None``) unless the known readings already prove No Travel.
    """
    wind, rain, snow = _clean(wind_mph), _clean(rain_in_hr), _clean(snow_in_hr)
    missing = tuple(n for n, v in (("wind", wind), ("rain", rain), ("snow", snow)) if v is None)

    levels: list[tuple[str, RiskLevel, str]] = []
    if wind is not None:
        levels.append(("wind", classify(wind, WIND_MPH), f"Wind {wind:.1f} mph"))
    if rain is not None:
        levels.append(("rain", classify(rain, RAIN_IN_HR), f"Rain {rain:.2f} in/hr"))
    if snow is not None:
        levels.append(("snow", classify(snow, SNOW_IN_HR), f"Snow {snow:.2f} in/hr"))

    base = max((lv for _, lv, _ in levels), default=None)
    floor = load_floor(wind, cargo_lb) if wind is not None else None

    drivers = [
        Driver(f, lv, f"{text} ({lv.label})") for f, lv, text in levels if lv >= RiskLevel.MODERATE
    ]
    if floor is not None and (base is None or floor[0] > base):
        drivers.append(Driver("load_rule", floor[0], f"{cargo_lb:,.0f} lb cargo: {floor[1]}"))

    candidates = [lv for lv in (base, floor[0] if floor else None) if lv is not None]
    top = max(candidates, default=None)

    if not missing:
        assert top is not None  # all three readings present
        return RiskAssessment(top, tuple(drivers))
    if top == RiskLevel.NO_TRAVEL:  # cannot get better than this whatever the missing data says
        return RiskAssessment(RiskLevel.NO_TRAVEL, tuple(drivers), missing)
    return RiskAssessment(None, tuple(drivers), missing, at_least=top)
