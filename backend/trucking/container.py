"""Wires providers from settings. Tests (and nothing else) replace the planner with ``override``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.conf import settings

from trucking.domain.types import LatLon
from trucking.planner import Planner
from trucking.services.geocoding.base import GeocodingProvider
from trucking.services.routing.base import RoutingError, RoutingProvider, RoutingResult
from trucking.services.weather.base import WeatherProvider
from trucking.services.weather.cache import DjangoCache
from trucking.services.weather.mock import MockWeatherProvider
from trucking.services.weather.open_meteo import OpenMeteoClient

_planner: Planner | None = None
_geocoder: GeocodingProvider | None = None


class _Unconfigured:
    """Stands in until a TomTom key is configured: every call explains what is missing."""

    name = "tomtom (not configured)"

    def get_routes(
        self, origin: LatLon, destination: LatLon, departure_utc: datetime
    ) -> RoutingResult:
        raise RoutingError("Routing is not configured on this server (missing TOMTOM_API_KEY).")

    def search(self, query: str, limit: int = 6) -> list[Any]:
        raise RoutingError("Geocoding is not configured on this server (missing TOMTOM_API_KEY).")


def _build_weather() -> WeatherProvider:
    if settings.WEATHER_PROVIDER == "mock":
        return MockWeatherProvider(settings.WEATHER_MOCK_SCENARIO)
    return OpenMeteoClient(cache=DjangoCache(), api_key=settings.OPEN_METEO_API_KEY)


def _build_routing() -> RoutingProvider:
    if not settings.TOMTOM_API_KEY:
        return _Unconfigured()  # type: ignore[return-value]
    from trucking.services.routing.tomtom import TomTomRouting

    return TomTomRouting(api_key=settings.TOMTOM_API_KEY, cache=DjangoCache())


def get_planner() -> Planner:
    global _planner
    if _planner is None:
        _planner = Planner(_build_routing(), _build_weather())
    return _planner


def get_geocoder() -> GeocodingProvider:
    global _geocoder
    if _geocoder is None:
        if not settings.TOMTOM_API_KEY:
            _geocoder = _Unconfigured()  # type: ignore[assignment]
        else:
            from trucking.services.geocoding.tomtom import TomTomGeocoder

            _geocoder = TomTomGeocoder(api_key=settings.TOMTOM_API_KEY, cache=DjangoCache())
    assert _geocoder is not None
    return _geocoder


def override(planner: Planner | None = None, geocoder: GeocodingProvider | None = None) -> None:
    global _planner, _geocoder
    _planner, _geocoder = planner, geocoder
