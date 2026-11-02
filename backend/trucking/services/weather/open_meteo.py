"""Open-Meteo client: batched multi-location hourly forecasts with caching and retries.

Facts verified by the spike (docs/spike/SPIKE_REPORT.md):
  * many locations per request; the response is a LIST in request order (a single location returns a
    dict); returned coordinates are grid-snapped, so results are matched by ORDER;
  * ``end_hour`` beyond today + 15 days is rejected with HTTP 400;
  * free API: non-commercial, CC BY 4.0, limits are per IP (shared hosts may hit them sooner).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from trucking.config import (
    WEATHER_CACHE_TTL_S,
    WEATHER_CHUNK_SIZE,
    WEATHER_FORECAST_LIMIT_DAYS,
    WEATHER_PARALLEL_REQUESTS,
)
from trucking.domain.forecast import HourlySeries
from trucking.domain.types import LatLon

from .base import (
    Cache,
    WeatherFormatError,
    WeatherResult,
    WeatherUnavailable,
    round_point,
)
from .normalize import HOURLY_VARIABLES, TIME_FORMAT, normalize_location

log = logging.getLogger(__name__)

FREE_URL = "https://api.open-meteo.com/v1/forecast"
PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"
MAX_ATTEMPTS = 3
# Open-Meteo's free tier has a per-minute location budget. A heatmap right after a plan can exceed it;
# waiting for the next minute is better than reporting Unknown, but only for the *minutely* limit.
MINUTELY_WAIT_S = 20.0
MINUTELY_MAX_WAITS = 3
TIMEOUT = httpx.Timeout(15.0, connect=3.0)


def floor_hour(t: datetime) -> datetime:
    return t.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


class OpenMeteoClient:
    name = "open-meteo"

    def __init__(
        self,
        *,
        cache: Cache,
        http: httpx.Client | None = None,
        api_key: str = "",
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_workers: int = WEATHER_PARALLEL_REQUESTS,
        chunk_size: int = WEATHER_CHUNK_SIZE,
    ) -> None:
        self._cache = cache
        self._http = http or httpx.Client(timeout=TIMEOUT)
        self._api_key = api_key
        self._sleep = sleep
        self._clock = clock
        self._max_workers = max_workers
        self._chunk_size = chunk_size

    # -- public ---------------------------------------------------------------------------
    def fetch(self, points: Sequence[LatLon], start: datetime, end: datetime) -> WeatherResult:
        start = floor_hour(start)
        end = min(floor_hour(end), self._latest_allowed_end())
        unique = list(dict.fromkeys(round_point(p) for p in points))
        result = WeatherResult(series={})
        if end < start:  # entirely beyond the forecast horizon: nothing can be known
            result.series = dict.fromkeys(unique)
            result.failed_points = len(unique)
            result.warnings.append("Requested times are beyond the weather forecast horizon.")
            return result

        misses: list[LatLon] = []
        for point in unique:
            cached = self._cache.get(self._key(point, start, end))
            if cached is not None:
                result.series[point] = cached
                result.cache_hits += 1
            else:
                misses.append(point)
        result.cache_misses = len(misses)

        chunks = [misses[i : i + self._chunk_size] for i in range(0, len(misses), self._chunk_size)]
        if chunks:
            with ThreadPoolExecutor(max_workers=min(self._max_workers, len(chunks))) as pool:
                outcomes = list(pool.map(lambda c: self._fetch_chunk(c, start, end), chunks))
            for chunk, (series_list, warning) in zip(chunks, outcomes, strict=True):
                if warning:
                    result.warnings.append(warning)
                for point, series in zip(chunk, series_list, strict=True):
                    result.series[point] = series
                    if series is None:
                        result.failed_points += 1
                    else:
                        self._cache.set(self._key(point, start, end), series, WEATHER_CACHE_TTL_S)
        return result

    # -- internals ------------------------------------------------------------------------
    def _latest_allowed_end(self) -> datetime:
        today = self._clock().astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return today + timedelta(days=WEATHER_FORECAST_LIMIT_DAYS)

    @staticmethod
    def _key(point: LatLon, start: datetime, end: datetime) -> str:
        return f"om:{point[0]:.2f}:{point[1]:.2f}:{start:%Y%m%d%H}:{end:%Y%m%d%H}"

    def _fetch_chunk(
        self, chunk: Sequence[LatLon], start: datetime, end: datetime
    ) -> tuple[list[HourlySeries | None], str | None]:
        """Series for each point of the chunk (same order) and an optional warning."""
        try:
            locations = self._request(chunk, start, end)
        except WeatherUnavailable as exc:
            log.warning("Open-Meteo chunk of %d points failed: %s", len(chunk), exc)
            return [None] * len(
                chunk
            ), f"Weather data unavailable for {len(chunk)} locations ({exc})."
        out: list[HourlySeries | None] = []
        bad = 0
        for location in locations:
            try:
                out.append(normalize_location(location))
            except WeatherFormatError as exc:
                log.warning("Open-Meteo location rejected: %s", exc)
                out.append(None)
                bad += 1
        warning = f"{bad} locations returned unusable weather data." if bad else None
        return out, warning

    def _request(
        self, chunk: Sequence[LatLon], start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "latitude": ",".join(f"{lat:.2f}" for lat, _ in chunk),
            "longitude": ",".join(f"{lon:.2f}" for _, lon in chunk),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "timezone": "GMT",
            "start_hour": start.strftime(TIME_FORMAT),
            "end_hour": end.strftime(TIME_FORMAT),
        }
        url = FREE_URL
        if self._api_key:
            params["apikey"] = self._api_key
            url = PAID_URL

        last_error = "unknown error"
        retry_after: int | None = None
        minutely_waits = 0
        attempt = 0
        while attempt < MAX_ATTEMPTS:
            attempt += 1
            delay = 0.0
            try:
                response = self._http.get(url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"network error: {type(exc).__name__}"
                delay = 0.5 * 2 ** (attempt - 1)
            else:
                if response.status_code == 200:
                    return self._parse(response, len(chunk))
                if response.status_code == 429:
                    reason = self._reason(response).lower()
                    last_error = "HTTP 429"
                    if "minute" in reason and minutely_waits < MINUTELY_MAX_WAITS:
                        minutely_waits += 1
                        attempt -= 1  # waiting out the minute is not a failed attempt
                        self._sleep(MINUTELY_WAIT_S)
                        continue
                    if "hour" in reason or "day" in reason:
                        # Retrying cannot help for a long time; fail fast so the user is told.
                        raise WeatherUnavailable("HTTP 429", retry_after_s=300)
                    header = response.headers.get("Retry-After", "")
                    retry_after = int(header) if header.isdigit() else None
                    delay = (
                        float(retry_after) if retry_after is not None else 0.5 * 2 ** (attempt - 1)
                    )
                elif response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                    delay = 0.5 * 2 ** (attempt - 1)
                else:  # 4xx such as an out-of-range window: retrying cannot help
                    raise WeatherUnavailable(
                        f"HTTP {response.status_code}: {self._reason(response)}"
                    )
            if attempt < MAX_ATTEMPTS:
                self._sleep(min(delay, 5.0))
        raise WeatherUnavailable(last_error, retry_after_s=retry_after or 30)

    @staticmethod
    def _reason(response: httpx.Response) -> str:
        try:
            return str(response.json().get("reason", ""))[:200]
        except ValueError:
            return response.text[:200]

    @staticmethod
    def _parse(response: httpx.Response, expected: int) -> list[dict[str, Any]]:
        try:
            data = response.json()
        except ValueError as exc:
            raise WeatherUnavailable("invalid JSON from weather provider") from exc
        locations = data if isinstance(data, list) else [data]  # single location -> dict
        if len(locations) != expected or not all(isinstance(loc, dict) for loc in locations):
            raise WeatherUnavailable(f"expected {expected} locations, got {len(locations)}")
        return locations
