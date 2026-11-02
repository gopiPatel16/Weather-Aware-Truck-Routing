"""Geocoding provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeocodeHit:
    label: str
    lat: float
    lon: float


class GeocodingProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 6) -> list[GeocodeHit]: ...
