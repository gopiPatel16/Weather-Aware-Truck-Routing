"""Hourly forecast series and the ETA -> forecast-interval matching policy (plan 5.4).

Open-Meteo semantics (verified, docs/spike/SPIKE_REPORT.md):
  * rain / showers / snowfall at stamp S are SUMS over the PRECEDING hour [S-1h, S).
  * wind (and gusts, temperature) at stamp S are INSTANTANEOUS values at S.

Policy for an arrival time t, with H = floor_to_hour(t) and f = t - H:
  * precipitation: the interval that COVERS t is [H, H+1h) -> the record stamped H+1h.
  * wind: linear interpolation between the records stamped H and H+1h.
  * conservative adjacency: if f < 15 min also evaluate the previous interval (stamp H); if
    f >= 45 min also evaluate the next interval (stamp H+2h); keep the WORSE result.
There is no "nearest hour" shortcut. The same function serves checkpoints and the heatmap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from trucking.config import ADJACENT_MARGIN

from .risk import assess_risk
from .types import RiskAssessment, RiskLevel

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class HourlySeries:
    """Normalised hourly forecast for one location (mph, inches in the hour, deg F), UTC stamps
    ``start, start+1h, ...``. ``None`` marks a missing value and is never treated as zero."""

    start: datetime
    wind_mph: tuple[float | None, ...]
    gust_mph: tuple[float | None, ...]
    rain_in: tuple[float | None, ...]  # rain + showers over the hour ending at the stamp
    snow_in: tuple[float | None, ...]  # snowfall over the hour ending at the stamp
    temp_f: tuple[float | None, ...]
    source_units: tuple[tuple[str, str], ...] = ()  # e.g. (("wind", "mp/h"), ("snow", "inch"))

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.start.utcoffset() != timedelta(0):
            raise ValueError("series start must be timezone-aware UTC")
        if (self.start.minute, self.start.second, self.start.microsecond) != (0, 0, 0):
            raise ValueError("series start must be on the hour")
        sizes = {
            len(self.wind_mph),
            len(self.gust_mph),
            len(self.rain_in),
            len(self.snow_in),
            len(self.temp_f),
        }
        if len(sizes) != 1:
            raise ValueError("all hourly arrays must have the same length")

    def __len__(self) -> int:
        return len(self.wind_mph)

    def value(self, values: tuple[float | None, ...], stamp: datetime) -> float | None:
        """Value at an hour-aligned stamp; ``None`` if the stamp is outside the series."""
        delta = stamp - self.start
        if delta % HOUR != timedelta(0):
            raise ValueError("stamp must be on the hour")
        index = delta // HOUR
        if index < 0 or index >= len(values):
            return None
        return values[index]


@dataclass(frozen=True)
class Candidate:
    """One precipitation interval [interval_start, interval_end) considered for a time t."""

    interval_start: datetime
    interval_end: datetime
    rain_in: float | None
    snow_in: float | None


@dataclass(frozen=True)
class ForecastSelection:
    t: datetime
    wind_mph: float | None
    gust_mph: float | None
    temp_f: float | None
    wind_stamps: tuple[datetime, datetime]
    candidates: tuple[Candidate, ...]  # candidates[0] is the covering interval

    @property
    def adjacent_interval_used(self) -> bool:
        return len(self.candidates) > 1


def _interpolate(
    series: HourlySeries, values: tuple[float | None, ...], h0: datetime, frac: float
) -> float | None:
    v0 = series.value(values, h0)
    if frac == 0.0:
        return v0
    v1 = series.value(values, h0 + HOUR)
    if v0 is None or v1 is None:
        return None
    return v0 + (v1 - v0) * frac


def select_forecast(
    series: HourlySeries, t: datetime, margin: timedelta = ADJACENT_MARGIN
) -> ForecastSelection:
    t = t.astimezone(UTC)
    h0 = t.replace(minute=0, second=0, microsecond=0)
    elapsed = t - h0
    frac = elapsed / HOUR

    stamps = [h0 + HOUR]  # covering interval [h0, h0+1h) is described by the record stamped h0+1h
    if elapsed < margin:
        stamps.append(h0)  # previous interval [h0-1h, h0)
    if elapsed >= HOUR - margin:
        stamps.append(h0 + 2 * HOUR)  # next interval [h0+1h, h0+2h)

    candidates = tuple(
        Candidate(s - HOUR, s, series.value(series.rain_in, s), series.value(series.snow_in, s))
        for s in stamps
    )
    return ForecastSelection(
        t=t,
        wind_mph=_interpolate(series, series.wind_mph, h0, frac),
        gust_mph=_interpolate(series, series.gust_mph, h0, frac),
        temp_f=_interpolate(series, series.temp_f, h0, frac),
        wind_stamps=(h0, h0 + HOUR),
        candidates=candidates,
    )


def assess_selection(
    selection: ForecastSelection, cargo_lb: float
) -> tuple[RiskAssessment, Candidate]:
    """Worst risk across the candidate intervals, plus the candidate that produced it."""
    results = [
        (assess_risk(selection.wind_mph, c.rain_in, c.snow_in, cargo_lb), c)
        for c in selection.candidates
    ]
    for assessment, candidate in results:
        if assessment.level == RiskLevel.NO_TRAVEL:
            return assessment, candidate
    primary, primary_candidate = results[0]
    if primary.level is None:  # covering interval unknown: adjacent data cannot make it known
        bounds = [a.level if a.level is not None else a.at_least for a, _ in results]
        known = [b for b in bounds if b is not None]
        return (
            RiskAssessment(None, primary.drivers, primary.missing, max(known, default=None)),
            primary_candidate,
        )
    known_results = [(a, c) for a, c in results if a.level is not None]
    return max(known_results, key=lambda pair: pair[0].level if pair[0].level is not None else -1)
