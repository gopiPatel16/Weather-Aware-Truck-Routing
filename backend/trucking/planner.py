"""Orchestration: routes -> checkpoints -> forecast -> risk -> coverage/eligibility -> ranking.

All rules live in ``trucking.domain``; this module only wires providers to them and shapes the
JSON-ready response documented in docs/PLAN.md section 7.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from trucking import config
from trucking.domain import polyline
from trucking.domain.checkpoints import Checkpoint, build_checkpoints, choose_interval
from trucking.domain.eta import TimeProfile, build_time_profile
from trucking.domain.forecast import assess_selection, select_forecast
from trucking.domain.geo import (
    METERS_PER_MILE,
    cumulative_miles,
    decimate,
    haversine_miles,
    sample_along,
    scale_to_length,
    simplify,
    slice_polyline,
)
from trucking.domain.heatmap import corridor_cells, hourly_levels, levels_string
from trucking.domain.route_filters import dedupe
from trucking.domain.scoring import (
    OwnedRisk,
    Recommendation,
    RouteScore,
    evaluate_eligibility,
    recommend,
    summarize,
)
from trucking.domain.timezones import (
    LocalDeparture,
    NonexistentLocalTime,
    TimeZoneLookupError,
    resolve_local,
    tz_name_at,
)
from trucking.domain.types import LatLon, RawRoute, RiskAssessment, level_key
from trucking.errors import ApiError
from trucking.services.routing.base import RoutingError, RoutingProvider
from trucking.services.weather.base import WeatherProvider, WeatherResult, round_point
from trucking.services.weather.open_meteo import floor_hour

log = logging.getLogger(__name__)
HOUR = timedelta(hours=1)
MAX_HEATMAP_CELLS = 2500
ALL_MISSING = ("wind", "rain", "snow")


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    @property
    def point(self) -> LatLon:
        return (self.lat, self.lon)


@dataclass(frozen=True)
class PlanInput:
    origin: Place
    destination: Place
    departure_local: datetime  # naive, interpreted in the ORIGIN's time zone
    cargo_weight_lb: float
    interval_miles: int


@dataclass
class _Prepared:
    route_id: str
    raw: RawRoute
    points: list[LatLon]
    cumulative: list[float]
    total_mi: float
    profile: TimeProfile
    checkpoints: list[Checkpoint] = field(default_factory=list)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coords(points: Sequence[LatLon]) -> list[list[float]]:
    return [[round(lon, 5), round(lat, 5)] for lat, lon in points]


def _weather_failure(weather: WeatherResult) -> ApiError:
    """Every forecast request failed. A provider rate limit gets its own message: retrying at once is useless."""
    if any("429" in w for w in weather.warnings):
        return ApiError(
            "rate_limited",
            "The free weather service's request limit has been reached. Wait a few minutes and try "
            "again (an hourly limit can take up to an hour to reset).",
            429,
            retry_after_s=300,
        )
    return ApiError(
        "weather_unavailable",
        "The weather forecast service is unavailable right now. Please try again shortly.",
        502,
        retry_after_s=30,
    )


class Planner:
    def __init__(
        self,
        routing: RoutingProvider,
        weather: WeatherProvider,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._routing = routing
        self._weather = weather
        self._clock = clock
        self._zones: dict[tuple[float, float], str] = {}

    # ------------------------------------------------------------------ plan --------------
    def plan(self, request: PlanInput) -> dict[str, Any]:
        started = time.perf_counter()
        timings: dict[str, int] = {}
        warnings: list[str] = []

        departure, origin_tz = self._resolve_departure(request, warnings)
        if (
            haversine_miles(request.origin.point, request.destination.point)
            < config.MIN_ROUTE_MILES
        ):
            raise ApiError(
                "validation_error", "Origin and destination are less than 5 miles apart.", 400
            )

        t = time.perf_counter()
        try:
            routing = self._routing.get_routes(
                request.origin.point, request.destination.point, departure.utc
            )
        except RoutingError as exc:
            raise ApiError(
                exc.code, exc.message, exc.status, retry_after_s=exc.retry_after_s
            ) from exc
        timings["routing"] = round((time.perf_counter() - t) * 1000)

        kept = dedupe(routing.routes)
        if not kept:
            raise ApiError(
                "no_route", "The routing provider found no truck route for this trip.", 422
            )
        prepared = [self._prepare(chr(ord("A") + i), raw) for i, raw in enumerate(kept[:3])]

        interval, adjusted = choose_interval(
            max(p.total_mi for p in prepared), request.interval_miles
        )
        if adjusted:
            warnings.append(
                f"Sampling interval raised from {request.interval_miles} to {interval} miles to keep the "
                f"trip within {config.MAX_CHECKPOINTS_PER_ROUTE} checkpoints."
            )
        for p in prepared:
            p.checkpoints = build_checkpoints(
                p.points, p.cumulative, p.profile, departure.utc, interval
            )

        t = time.perf_counter()
        longest = max(p.raw.duration_s for p in prepared)
        weather = self._weather.fetch(
            [(cp.lat, cp.lon) for p in prepared for cp in p.checkpoints],
            departure.utc,
            departure.utc + timedelta(seconds=longest) + 2 * HOUR,
        )
        timings["weather"] = round((time.perf_counter() - t) * 1000)
        if weather.all_failed:
            raise _weather_failure(weather)
        warnings.extend(weather.warnings)

        routes_out: list[dict[str, Any]] = []
        scores: list[RouteScore] = []
        for p in prepared:
            out, score = self._assess_route(
                p, weather, request.cargo_weight_lb, departure, warnings
            )
            routes_out.append(out)
            scores.append(score)
        recommendation = recommend(scores)

        timings["total"] = round((time.perf_counter() - started) * 1000)
        return {
            "request": {
                "origin_timezone": origin_tz,
                "departure_local": departure.local_iso,
                "departure_utc": iso_utc(departure.utc),
                "interval_miles": interval,
                "requested_interval_miles": request.interval_miles,
                "interval_adjusted": adjusted,
                "cargo_weight_lb": request.cargo_weight_lb,
                "warnings": warnings,
            },
            "alternatives": self._alternatives(
                routing.requested, len(routing.routes), len(prepared)
            ),
            "routes": routes_out,
            "recommendation": self._present_recommendation(recommendation),
            "meta": {
                "routing_provider": self._routing.name,
                "weather_provider": self._weather.name,
                "weather_model": "best_match"
                if self._weather.name == "open-meteo"
                else "synthetic demo data",
                "timings_ms": timings,
                "weather_cache": {"hits": weather.cache_hits, "misses": weather.cache_misses},
            },
        }

    # --------------------------------------------------------------- heatmap --------------
    def heatmap(
        self,
        routes: Sequence[tuple[str, Sequence[LatLon]]],
        departure_utc: datetime,
        cargo_lb: float,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        samples = [
            sample_along(pts, cumulative_miles(pts), config.HEATMAP_ROUTE_SAMPLE_MILES)
            for _, pts in routes
        ]
        cells = corridor_cells(samples, config.HEATMAP_CELL_MILES, config.HEATMAP_HALF_WIDTH_MILES)
        if len(cells) > MAX_HEATMAP_CELLS:
            raise ApiError("validation_error", "The corridor is too large for a heatmap.", 400)

        start = floor_hour(departure_utc)
        t = time.perf_counter()
        weather = self._weather.fetch(
            [(c.lat, c.lon) for c in cells], start, start + (config.HEATMAP_HOURS + 2) * HOUR
        )
        weather_ms = round((time.perf_counter() - t) * 1000)
        if weather.all_failed:
            raise _weather_failure(weather)

        out_cells = []
        unknown_cells = 0
        for cell in cells:
            series = weather.series.get(round_point((cell.lat, cell.lon)))
            levels = hourly_levels(series, departure_utc, cargo_lb)
            if all(lv is None for lv in levels):
                unknown_cells += 1
            out_cells.append(
                {
                    "lat": round(cell.lat, 4),
                    "lon": round(cell.lon, 4),
                    "levels": levels_string(levels),
                }
            )
        return {
            "start_utc": iso_utc(departure_utc),
            "hours": config.HEATMAP_HOURS + 1,
            "cell_miles": config.HEATMAP_CELL_MILES,
            "half_width_miles": config.HEATMAP_HALF_WIDTH_MILES,
            "cells": out_cells,
            "meta": {
                "cells": len(out_cells),
                "unknown_cells": unknown_cells,
                "weather_provider": self._weather.name,
                "warnings": weather.warnings,
                "timings_ms": {
                    "weather": weather_ms,
                    "total": round((time.perf_counter() - started) * 1000),
                },
                "weather_cache": {"hits": weather.cache_hits, "misses": weather.cache_misses},
            },
        }

    # ------------------------------------------------------------- internals -------------
    def _resolve_departure(
        self, request: PlanInput, warnings: list[str]
    ) -> tuple[LocalDeparture, str]:
        try:
            tz_name = tz_name_at(*request.origin.point)
        except TimeZoneLookupError as exc:
            raise ApiError(
                "validation_error", f"Could not determine the origin's time zone: {exc}", 400
            ) from exc
        try:
            departure = resolve_local(request.departure_local, tz_name)
        except NonexistentLocalTime as exc:
            raise ApiError(
                "invalid_departure_time", str(exc), 400, fields={"departure_local": [str(exc)]}
            ) from exc
        now = self._clock()
        if (
            departure.utc < now - config.DEPARTURE_GRACE
            or departure.utc > now + config.MAX_DEPARTURE_AHEAD
        ):
            raise ApiError(
                "invalid_departure_time",
                f"Departure must be between now and {config.MAX_DEPARTURE_AHEAD.days} days from now "
                f"(time zone {tz_name}).",
                400,
                fields={"departure_local": ["Choose a time from now up to 7 days ahead."]},
            )
        if departure.ambiguous and departure.other_utc is not None:
            warnings.append(
                f"{request.departure_local:%Y-%m-%d %H:%M} occurs twice in {tz_name} (clocks change). "
                f"Using the first occurrence ({departure.local_iso}); the second would be "
                f"{iso_utc(departure.other_utc)}."
            )
        return departure, tz_name

    def _prepare(self, route_id: str, raw: RawRoute) -> _Prepared:
        total_mi = raw.distance_m / METERS_PER_MILE
        if total_mi > config.MAX_ROUTE_MILES:
            raise ApiError(
                "trip_too_long",
                f"This trip is longer than {config.MAX_ROUTE_MILES:.0f} miles.",
                422,
            )
        if total_mi < config.MIN_ROUTE_MILES:
            raise ApiError(
                "validation_error", "Origin and destination are less than 5 miles apart.", 400
            )
        points = decimate(raw.points, config.GEOMETRY_MIN_SPACING_M)
        cumulative = scale_to_length(cumulative_miles(points), total_mi)
        profile = build_time_profile(raw.time_offsets, raw.distance_m, raw.duration_s)
        return _Prepared(route_id, raw, points, cumulative, total_mi, profile)

    def _zone(self, lat: float, lon: float, previous: str) -> str:
        key = (round(lat, 1), round(lon, 1))
        if key not in self._zones:
            try:
                self._zones[key] = tz_name_at(lat, lon)
            except TimeZoneLookupError:
                return previous
        return self._zones[key]

    def _assess_route(
        self,
        p: _Prepared,
        weather: WeatherResult,
        cargo_lb: float,
        departure: LocalDeparture,
        warnings: list[str],
    ) -> tuple[dict[str, Any], RouteScore]:
        owned: list[OwnedRisk] = []
        checkpoints_out: list[dict[str, Any]] = []
        levels_for_segments = []
        zone = departure.tz_name
        for cp in p.checkpoints:
            series = weather.series.get(round_point((cp.lat, cp.lon)))
            weather_out: dict[str, Any] | None = None
            if series is None:
                assessment = RiskAssessment(None, (), ALL_MISSING)
            else:
                selection = select_forecast(series, cp.eta_utc)
                assessment, candidate = assess_selection(selection, cargo_lb)
                weather_out = {
                    "wind_mph": _r(selection.wind_mph, 1),
                    "gust_mph": _r(selection.gust_mph, 1),
                    "rain_in_hr": _r(candidate.rain_in, 3),
                    "snow_in_hr": _r(candidate.snow_in, 3),
                    "temp_f": _r(selection.temp_f, 0),
                    "basis": {
                        "precip_intervals": [
                            [iso_utc(c.interval_start), iso_utc(c.interval_end)]
                            for c in selection.candidates
                        ],
                        "wind_stamps": [iso_utc(s) for s in selection.wind_stamps],
                        "adjacent_interval_used": selection.adjacent_interval_used,
                    },
                    "source_units": dict(series.source_units),
                }
            owned.append(OwnedRisk(cp.owned_miles, assessment.level))
            levels_for_segments.append(assessment.level)
            zone = self._zone(cp.lat, cp.lon, zone)
            checkpoints_out.append(
                {
                    "i": cp.index,
                    "mile": round(cp.mile, 1),
                    "lat": round(cp.lat, 5),
                    "lon": round(cp.lon, 5),
                    "eta_utc": iso_utc(cp.eta_utc),
                    "tz": zone,
                    "weather": weather_out,
                    "risk": {
                        "level": level_key(assessment.level),
                        "score": None if assessment.level is None else int(assessment.level),
                        "at_least": None
                        if assessment.at_least is None
                        else assessment.at_least.key,
                        "missing": list(assessment.missing),
                        "drivers": [
                            {"factor": d.factor, "level": d.level.key, "text": d.text}
                            for d in assessment.drivers
                        ],
                    },
                }
            )

        metrics = summarize(owned)
        eligibility = evaluate_eligibility(metrics)
        name = f"Route {p.route_id}"
        if p.profile.method != "route_guidance":
            warnings.append(
                f"ETAs for {name} are estimated from average speed (route timing data unavailable)."
            )
        if metrics.coverage < 1.0:
            warnings.append(
                f"{name}: weather forecast covers only {metrics.coverage * 100:.1f}% of the route."
            )

        display = simplify(p.points, config.DISPLAY_SIMPLIFY_TOLERANCE_M)
        display_cum = scale_to_length(cumulative_miles(display), p.total_mi)
        segments = self._segments(display, display_cum, p.checkpoints, levels_for_segments)
        arrival = p.checkpoints[-1].eta_utc
        out = {
            "id": p.route_id,
            "name": name,
            "via": p.raw.via,
            "distance_mi": round(p.total_mi, 1),
            "duration_s": round(p.raw.duration_s),
            "arrival_utc": iso_utc(arrival),
            "arrival_tz": checkpoints_out[-1]["tz"],
            "eta_method": p.profile.method,
            "geometry": {"type": "LineString", "coordinates": _coords(display)},
            "polyline": polyline.encode(display),
            "segments": segments,
            "summary": {
                "miles_by_level": {k: round(v, 1) for k, v in metrics.miles_by_level.items()},
                "coverage_pct": round(metrics.coverage * 100, 1),
                "no_travel_mi": round(metrics.no_travel_mi, 1),
                "severe_mi": round(metrics.severe_mi, 1),
                "high_mi": round(metrics.high_mi, 1),
                "avg_risk": None if metrics.avg_risk is None else round(metrics.avg_risk, 2),
                "max_level": level_key(metrics.max_level)
                if metrics.max_level is not None
                else "unknown",
                "checkpoint_count": len(p.checkpoints),
            },
            "eligibility": {"eligible": eligibility.eligible, "reasons": list(eligibility.reasons)},
            "checkpoints": checkpoints_out,
        }
        return out, RouteScore(p.route_id, metrics, eligibility, p.raw.duration_s)

    @staticmethod
    def _segments(
        points: Sequence[LatLon],
        cumulative: Sequence[float],
        checkpoints: Sequence[Checkpoint],
        levels: Sequence[Any],
    ) -> list[dict[str, Any]]:
        """Risk-coloured display segments; neighbouring stretches with the same level are merged."""
        merged: list[list[Any]] = []  # [from_mi, to_mi, level]
        for cp, level in zip(checkpoints, levels, strict=True):
            if merged and merged[-1][2] == level:
                merged[-1][1] = cp.owns_to_mi
            else:
                merged.append([cp.owns_from_mi, cp.owns_to_mi, level])
        return [
            {
                "from_mi": round(a, 1),
                "to_mi": round(b, 1),
                "level": level_key(level),
                "coordinates": _coords(slice_polyline(points, cumulative, a, b)),
            }
            for a, b, level in merged
        ]

    @staticmethod
    def _alternatives(requested: int, returned: int, usable: int) -> dict[str, Any]:
        if usable <= 1:
            message = "The routing provider returned only 1 route for this trip; no alternatives were available."
        else:
            message = f"The routing provider returned {usable} valid alternatives for this trip."
        if returned > usable:
            message += f" ({returned - usable} near-duplicate route(s) removed.)"
        return {"requested": requested, "returned": returned, "usable": usable, "message": message}

    @staticmethod
    def _present_recommendation(rec: Recommendation) -> dict[str, Any]:
        return {
            "status": rec.status,
            "route_id": rec.route_id,
            "ranking": list(rec.ranking),
            "headline": rec.headline,
            "reasons": list(rec.reasons),
            "caveats": list(rec.caveats),
        }


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)
