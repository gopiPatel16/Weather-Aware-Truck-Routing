"""TomTom truck routing adapter.

Verified against the live API (docs/spike/tomtom/, SPIKE_REPORT.md):
  * ``travelMode=truck`` with ``maxAlternatives=2`` returns up to 3 routes;
  * every route carries an encoded polyline (precision 5) and ``guidance.instructions`` with
    ``routeOffsetInMeters`` / ``travelTimeInSeconds`` - the source of per-checkpoint ETAs;
  * ``vehicleWeight`` means the *vehicle's* weight, not cargo, so cargo weight is never sent (plan D8).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from trucking.config import ROUTES_REQUESTED, ROUTING_CACHE_TTL_S
from trucking.domain.polyline import decode
from trucking.domain.types import LatLon, RawRoute
from trucking.services.weather.base import Cache

from .base import NoRouteFound, RoutingError, RoutingQuotaExceeded, RoutingResult

log = logging.getLogger(__name__)

BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
MAX_ATTEMPTS = 3
TIMEOUT = httpx.Timeout(25.0, connect=5.0)
MAX_ALTERNATIVES = ROUTES_REQUESTED - 1


class TomTomRouting:
    name = "tomtom"

    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.Client | None = None,
        cache: Cache | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._key = api_key
        self._http = http or httpx.Client(timeout=TIMEOUT)
        self._cache = cache
        self._sleep = sleep

    # -- public ---------------------------------------------------------------------------
    def get_routes(
        self, origin: LatLon, destination: LatLon, departure_utc: datetime
    ) -> RoutingResult:
        depart = departure_utc.astimezone(UTC).replace(microsecond=0)
        cache_key = (
            f"tt:{origin[0]:.4f},{origin[1]:.4f}:{destination[0]:.4f},{destination[1]:.4f}"
            f":{depart:%Y%m%d%H}"
        )
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached  # type: ignore[no-any-return]

        body = self._request(origin, destination, depart)
        routes = tuple(r for r in (_parse_route(raw) for raw in body.get("routes", [])) if r)
        if not routes:
            raise NoRouteFound("The routing provider found no truck route for this trip.")
        result = RoutingResult(routes, requested=ROUTES_REQUESTED)
        if self._cache is not None:
            self._cache.set(cache_key, result, ROUTING_CACHE_TTL_S)
        return result

    # -- internals ------------------------------------------------------------------------
    @staticmethod
    def _params(depart: datetime) -> dict[str, str]:
        # Deliberately absent: vehicleWeight and every other vehicle spec (plan D8).
        return {
            "travelMode": "truck",
            "routeType": "fastest",
            "traffic": "true",
            "maxAlternatives": str(MAX_ALTERNATIVES),
            "departAt": depart.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "routeRepresentation": "encodedPolyline",
            "instructionsType": "coded",
            "computeTravelTimeFor": "all",
        }

    def _request(self, origin: LatLon, destination: LatLon, depart: datetime) -> dict[str, Any]:
        locations = f"{origin[0]:.6f},{origin[1]:.6f}:{destination[0]:.6f},{destination[1]:.6f}"
        url = f"{BASE_URL}/{locations}/json"
        params = {**self._params(depart), "key": self._key}
        last: str = "The routing service did not respond."
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._http.get(url, params=params)
            except httpx.HTTPError as exc:  # timeout, connection, TLS ...
                last = f"The routing service could not be reached ({type(exc).__name__})."
                log.warning("tomtom request failed: %s", type(exc).__name__)
            else:
                status = response.status_code
                if status == 200:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise RoutingError(
                            "The routing service returned an invalid response."
                        ) from exc
                    if not isinstance(data, dict):
                        raise RoutingError("The routing service returned an invalid response.")
                    return data
                if status in (401, 403):
                    raise RoutingError("The routing service rejected the server's API key.")
                if status == 429:
                    retry = _retry_after(response)
                    raise RoutingQuotaExceeded(
                        "The routing service is rate limited right now.", retry_after_s=retry
                    )
                if status == 400:
                    raise NoRouteFound(_error_text(response) or "No truck route could be found.")
                last = f"The routing service is busy (HTTP {status})."
            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(0.5 * (2**attempt))
        raise RoutingError(last, retry_after_s=20)


def _retry_after(response: httpx.Response) -> int:
    try:
        return max(1, min(300, int(response.headers.get("Retry-After", "30"))))
    except ValueError:
        return 30


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return ""
    if isinstance(data, dict):
        detail = data.get("detailedError")
        if isinstance(detail, dict) and detail.get("message"):
            return str(detail["message"])[:200]
    return ""


def _parse_route(raw: dict[str, Any]) -> RawRoute | None:
    """One TomTom route -> RawRoute, or None when geometry, length or duration is missing."""
    try:
        summary = raw["summary"]
        distance_m = float(summary["lengthInMeters"])
        duration_s = float(summary["travelTimeInSeconds"])
        points: list[LatLon] = []
        for leg in raw["legs"]:
            leg_points = decode(leg["encodedPolyline"], int(leg.get("encodedPolylinePrecision", 5)))
            points.extend(leg_points[1:] if points and leg_points else leg_points)
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if len(points) < 2 or distance_m <= 0 or duration_s <= 0:
        return None
    instructions = (raw.get("guidance") or {}).get("instructions") or []
    return RawRoute(
        points=tuple(points),
        distance_m=distance_m,
        duration_s=duration_s,
        time_offsets=_time_offsets(instructions),
        via=_via_label(instructions, distance_m),
    )


def _time_offsets(instructions: list[dict[str, Any]]) -> tuple[tuple[float, float], ...]:
    pairs: list[tuple[float, float]] = []
    for step in instructions:
        try:
            pairs.append((float(step["routeOffsetInMeters"]), float(step["travelTimeInSeconds"])))
        except (KeyError, TypeError, ValueError):
            return ()  # unusable guidance: the planner falls back to (flagged) uniform speed
    return tuple(pairs)


def _via_label(instructions: list[dict[str, Any]], total_m: float) -> str | None:
    """Road number (e.g. "I-80 W") that carries the most distance; falls back to the street name."""
    by_road: dict[str, float] = defaultdict(float)
    by_street: dict[str, float] = defaultdict(float)
    for i, step in enumerate(instructions):
        try:
            start = float(step["routeOffsetInMeters"])
            end = (
                float(instructions[i + 1]["routeOffsetInMeters"])
                if i + 1 < len(instructions)
                else total_m
            )
        except (KeyError, TypeError, ValueError):
            continue
        length = max(0.0, end - start)
        roads = step.get("roadNumbers")
        if isinstance(roads, list) and roads:
            by_road[str(roads[0])] += length
        elif step.get("street"):
            by_street[str(step["street"])] += length
    pool = by_road or by_street
    return max(pool, key=lambda k: pool[k]) if pool else None
