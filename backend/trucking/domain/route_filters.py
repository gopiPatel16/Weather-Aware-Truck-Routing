"""Honest de-duplication of provider-returned routes (plan 5.1). Nothing is ever invented here:
we only drop a returned route that is a near-duplicate of a faster one."""

from __future__ import annotations

from collections.abc import Sequence

from trucking.config import (
    DUPLICATE_METRIC_TOLERANCE,
    DUPLICATE_SHARE,
    DUPLICATE_WITHIN_MILES,
)

from .geo import cumulative_miles, haversine_miles, sample_along
from .types import LatLon, RawRoute

_CELL_DEG = 0.02  # >= 0.5 mi in both axes up to ~70 deg latitude


def _cell(p: LatLon) -> tuple[int, int]:
    return int(p[0] // _CELL_DEG), int(p[1] // _CELL_DEG)


def share_ratio(
    a: Sequence[LatLon], b: Sequence[LatLon], within_miles: float = DUPLICATE_WITHIN_MILES
) -> float:
    """Fraction of route A (sampled every 2 mi) that lies within ``within_miles`` of route B
    (densified every 0.25 mi, so gaps between polyline vertices cannot hide a shared road)."""
    sample_a = sample_along(a, cumulative_miles(a), 2.0)
    dense_b = sample_along(b, cumulative_miles(b), 0.25)
    grid: dict[tuple[int, int], list[LatLon]] = {}
    for p in dense_b:
        grid.setdefault(_cell(p), []).append(p)
    close = 0
    for p in sample_a:
        cx, cy = _cell(p)
        near = (
            q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((cx + dx, cy + dy), ())
        )
        if any(haversine_miles(p, q) <= within_miles for q in near):
            close += 1
    return close / len(sample_a)


def _within(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance * max(a, b)


def is_duplicate(a: RawRoute, b: RawRoute) -> bool:
    return (
        _within(a.distance_m, b.distance_m, DUPLICATE_METRIC_TOLERANCE)
        and _within(a.duration_s, b.duration_s, DUPLICATE_METRIC_TOLERANCE)
        and share_ratio(a.points, b.points) >= DUPLICATE_SHARE
        and share_ratio(b.points, a.points) >= DUPLICATE_SHARE
    )


def dedupe(routes: Sequence[RawRoute]) -> list[RawRoute]:
    """Fastest first; a route is dropped only if it duplicates one already kept."""
    kept: list[RawRoute] = []
    for route in sorted(routes, key=lambda r: r.duration_s):
        if not any(is_duplicate(k, route) for k in kept):
            kept.append(route)
    return kept
