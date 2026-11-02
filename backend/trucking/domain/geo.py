"""Geometry helpers (pure Python): distances, decimation, interpolation along a polyline,
simplification and slicing. All distances are in miles unless the name says otherwise."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence

from .types import LatLon

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344
MILES_PER_DEGREE = EARTH_RADIUS_MI * math.pi / 180  # ~69.09 mi per degree of latitude


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def _planar_miles(a: LatLon, b: LatLon) -> float:
    """Cheap equirectangular distance, good enough for sub-mile decisions."""
    dy = (b[0] - a[0]) * MILES_PER_DEGREE
    dx = (b[1] - a[1]) * MILES_PER_DEGREE * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def decimate(points: Sequence[LatLon], min_spacing_m: float) -> list[LatLon]:
    """Keep a point only if it is at least ``min_spacing_m`` from the last kept one (ends kept)."""
    if len(points) <= 2:
        return list(points)
    min_mi = min_spacing_m / METERS_PER_MILE
    kept = [points[0]]
    last = points[0]
    for p in points[1:-1]:
        if _planar_miles(last, p) >= min_mi:
            kept.append(p)
            last = p
    kept.append(points[-1])
    return kept


def cumulative_miles(points: Sequence[LatLon]) -> list[float]:
    out = [0.0]
    for i in range(1, len(points)):
        out.append(out[-1] + haversine_miles(points[i - 1], points[i]))
    return out


def scale_to_length(cumulative: Sequence[float], total_miles: float) -> list[float]:
    """Scale cumulative distances so the last one equals the provider's reported length."""
    if not cumulative or cumulative[-1] <= 0:
        raise ValueError("route has zero length")
    factor = total_miles / cumulative[-1]
    return [c * factor for c in cumulative]


def point_at(points: Sequence[LatLon], cumulative: Sequence[float], miles: float) -> LatLon:
    """Position ``miles`` along the polyline (clamped to its ends), linear between vertices."""
    if miles <= 0:
        return points[0]
    if miles >= cumulative[-1]:
        return points[-1]
    i = bisect_right(cumulative, miles) - 1
    span = cumulative[i + 1] - cumulative[i]
    t = (miles - cumulative[i]) / span if span > 0 else 0.0
    (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


def slice_polyline(
    points: Sequence[LatLon], cumulative: Sequence[float], from_mi: float, to_mi: float
) -> list[LatLon]:
    """Sub-polyline between two distances, including interpolated end points."""
    out = [point_at(points, cumulative, from_mi)]
    lo = bisect_right(cumulative, from_mi)
    hi = bisect_right(cumulative, to_mi)
    out.extend(points[lo:hi])
    end = point_at(points, cumulative, to_mi)
    if out[-1] != end:
        out.append(end)
    return out


def sample_along(
    points: Sequence[LatLon], cumulative: Sequence[float], step_mi: float
) -> list[LatLon]:
    """Points every ``step_mi`` along the polyline, always including the end."""
    total = cumulative[-1]
    out: list[LatLon] = []
    d = 0.0
    while d < total:
        out.append(point_at(points, cumulative, d))
        d += step_mi
    out.append(points[-1])
    return out


def _point_segment_miles(p: LatLon, a: LatLon, b: LatLon) -> float:
    cos_lat = math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * cos_lat, a[0] - p[0]
    bx, by = (b[1] - p[1]) * cos_lat, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.hypot(ax + t * dx, ay + t * dy) * MILES_PER_DEGREE


def simplify(points: Sequence[LatLon], tolerance_m: float) -> list[LatLon]:
    """Douglas-Peucker (iterative) - used only for geometry sent to the browser."""
    n = len(points)
    if n <= 2:
        return list(points)
    tol_mi = tolerance_m / METERS_PER_MILE
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        far, far_d = -1, 0.0
        for i in range(lo + 1, hi):
            d = _point_segment_miles(points[i], points[lo], points[hi])
            if d > far_d:
                far, far_d = i, d
        if far_d > tol_mi:
            keep[far] = True
            stack.append((lo, far))
            stack.append((far, hi))
    return [p for p, k in zip(points, keep, strict=True) if k]
