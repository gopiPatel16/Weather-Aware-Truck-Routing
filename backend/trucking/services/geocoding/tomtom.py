"""TomTom Search (typeahead) adapter. Time zones are NOT in the response; the API view adds them offline."""

from __future__ import annotations

import logging
import time
import urllib.parse
from collections.abc import Callable

import httpx

from trucking.config import GEOCODE_CACHE_TTL_S
from trucking.services.routing.base import RoutingError, RoutingQuotaExceeded
from trucking.services.weather.base import Cache

from .base import GeocodeHit

log = logging.getLogger(__name__)

BASE_URL = "https://api.tomtom.com/search/2/search"
TIMEOUT = httpx.Timeout(8.0, connect=3.0)
MAX_ATTEMPTS = 2


class TomTomGeocoder:
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

    def search(self, query: str, limit: int = 6) -> list[GeocodeHit]:
        query = " ".join(query.split())
        cache_key = f"tg:{query.lower()}:{limit}"
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached  # type: ignore[no-any-return]
        url = f"{BASE_URL}/{urllib.parse.quote(query, safe='')}.json"
        params = {
            "typeahead": "true",
            "limit": str(limit),
            "countrySet": "US,CA",
            "key": self._key,
        }
        hits = _parse(self._get(url, params), limit)
        if self._cache is not None:
            self._cache.set(cache_key, hits, GEOCODE_CACHE_TTL_S)
        return hits

    def _get(self, url: str, params: dict[str, str]) -> dict:  # type: ignore[type-arg]
        last = "The place search service could not be reached."
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                last = f"The place search service could not be reached ({type(exc).__name__})."
            else:
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise RoutingError(
                            "The place search returned an invalid response."
                        ) from exc
                    return data if isinstance(data, dict) else {}
                if response.status_code in (401, 403):
                    raise RoutingError("The place search rejected the server's API key.")
                if response.status_code == 429:
                    raise RoutingQuotaExceeded(
                        "The place search is rate limited right now.", retry_after_s=30
                    )
                last = f"The place search is busy (HTTP {response.status_code})."
            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(0.3)
        raise RoutingError(last, retry_after_s=10)


def _parse(body: dict, limit: int) -> list[GeocodeHit]:  # type: ignore[type-arg]
    hits: list[GeocodeHit] = []
    seen: set[str] = set()
    for item in body.get("results", []):
        try:
            label = str(item["address"]["freeformAddress"]).strip()
            lat = float(item["position"]["lat"])
            lon = float(item["position"]["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        country = str(item["address"].get("countryCode", ""))
        if label and label.lower() not in seen:
            seen.add(label.lower())
            hits.append(
                GeocodeHit(
                    f"{label}, {country}" if country and country not in label else label, lat, lon
                )
            )
    return hits[:limit]
