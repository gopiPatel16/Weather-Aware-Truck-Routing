"""Cumulative ETA along a route (plan 5.4).

Preferred: piecewise-linear interpolation through the routing provider's own
(metres from start, seconds from start) guidance points. If those are missing or unusable the
fallback is a uniform average speed, and the profile says so (``method``) so the UI can flag the
ETAs as estimated.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

GUIDANCE = "route_guidance"
ESTIMATED = "estimated_uniform_speed"


@dataclass(frozen=True)
class TimeProfile:
    meters: tuple[float, ...]
    seconds: tuple[float, ...]
    method: str

    def seconds_at(self, meters: float) -> float:
        if meters <= self.meters[0]:
            return self.seconds[0]
        if meters >= self.meters[-1]:
            return self.seconds[-1]
        i = bisect_right(self.meters, meters) - 1
        span = self.meters[i + 1] - self.meters[i]
        frac = (meters - self.meters[i]) / span if span > 0 else 0.0
        return self.seconds[i] + (self.seconds[i + 1] - self.seconds[i]) * frac


def _usable_guidance(
    offsets: Sequence[tuple[float, float]], total_m: float, total_s: float
) -> list[tuple[float, float]] | None:
    pts = sorted(
        (min(m, total_m), s) for m, s in offsets if m >= 0 and s >= 0 and m <= total_m * 1.001
    )
    if len(pts) < 2:
        return None
    seconds = [s for _, s in pts]
    if any(b < a for a, b in zip(seconds, seconds[1:], strict=False)):
        return None  # time must never go backwards along the route
    if pts[-1][0] < 0.98 * total_m or pts[-1][1] > total_s * 1.001:
        return None  # guidance must reach the end of the route and agree with the total duration
    merged: dict[float, float] = {}
    for m, s in pts:
        merged[m] = max(s, merged.get(m, 0.0))
    merged.setdefault(0.0, 0.0)
    merged[total_m] = max(total_s, merged.get(total_m, 0.0))
    return sorted(merged.items())


def build_time_profile(
    offsets: Sequence[tuple[float, float]], total_m: float, total_s: float
) -> TimeProfile:
    if total_m <= 0 or total_s <= 0:
        raise ValueError("route needs a positive length and duration")
    pts = _usable_guidance(offsets, total_m, total_s) if offsets else None
    if pts is None:
        return TimeProfile((0.0, total_m), (0.0, total_s), ESTIMATED)
    return TimeProfile(tuple(m for m, _ in pts), tuple(s for _, s in pts), GUIDANCE)
