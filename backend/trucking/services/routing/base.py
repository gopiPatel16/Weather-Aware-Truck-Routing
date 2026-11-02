"""Routing provider contract. The planner depends on this Protocol, never on a vendor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from trucking.domain.types import LatLon, RawRoute


class RoutingError(Exception):
    code = "routing_unavailable"
    status = 502

    def __init__(self, message: str, *, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_s = retry_after_s


class NoRouteFound(RoutingError):
    code = "no_route"
    status = 422


class RoutingQuotaExceeded(RoutingError):
    code = "quota_exceeded"
    status = 503


@dataclass(frozen=True)
class RoutingResult:
    routes: tuple[RawRoute, ...]  # exactly what the provider returned - nothing added
    requested: int


class RoutingProvider(Protocol):
    name: str

    def get_routes(
        self, origin: LatLon, destination: LatLon, departure_utc: datetime
    ) -> RoutingResult:
        """Native truck-mode routes (the provider's own alternatives). Never fabricated."""
        ...
