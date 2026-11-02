"""Route metrics, eligibility and ranking (plan 5.7).

Eligibility and ranking are separate:
  * ELIGIBLE  = no No-Travel miles AND complete weather coverage. These are hard gates.
  * RANKING   = eligible routes only, by (Severe miles, High miles, average risk, duration).
No Travel is never a ranking tier and a blocked route is never recommended.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from trucking.config import MIN_COVERAGE_FOR_RECOMMENDATION

from .types import RiskLevel

BLOCKED_NO_TRAVEL = "no_travel"
BLOCKED_INCOMPLETE = "incomplete_weather"

RECOMMENDED = "recommended"
NO_SAFE_ROUTE = "no_safe_route"
INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class OwnedRisk:
    """Risk (or Unknown = None) for the stretch of route a checkpoint owns."""

    miles: float
    level: RiskLevel | None


@dataclass(frozen=True)
class RouteMetrics:
    total_mi: float
    miles_by_level: dict[str, float]  # low, moderate, high, severe, no_travel, unknown
    coverage: float  # 0..1, share of route miles with a known risk
    no_travel_mi: float
    severe_mi: float
    high_mi: float
    avg_risk: float | None  # distance-weighted over known miles, scores Low 0 .. No Travel 4
    max_level: RiskLevel | None


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    metrics: RouteMetrics
    eligibility: Eligibility
    duration_s: float


@dataclass(frozen=True)
class Recommendation:
    status: str
    route_id: str | None
    ranking: tuple[str, ...]
    headline: str
    reasons: tuple[str, ...]
    caveats: tuple[str, ...]


def summarize(owned: Sequence[OwnedRisk]) -> RouteMetrics:
    total = sum(o.miles for o in owned)
    by_level = {lv.key: 0.0 for lv in RiskLevel}
    by_level["unknown"] = 0.0
    weighted = known = 0.0
    max_level: RiskLevel | None = None
    for item in owned:
        if item.level is None:
            by_level["unknown"] += item.miles
            continue
        by_level[item.level.key] += item.miles
        weighted += int(item.level) * item.miles
        known += item.miles
        max_level = item.level if max_level is None else max(max_level, item.level)
    coverage = 1.0 - by_level["unknown"] / total if total > 0 else 0.0
    return RouteMetrics(
        total_mi=total,
        miles_by_level=by_level,
        coverage=coverage,
        no_travel_mi=by_level["no_travel"],
        severe_mi=by_level["severe"],
        high_mi=by_level["high"],
        avg_risk=weighted / known if known > 0 else None,
        max_level=max_level,
    )


def evaluate_eligibility(
    metrics: RouteMetrics, min_coverage: float = MIN_COVERAGE_FOR_RECOMMENDATION
) -> Eligibility:
    reasons: list[str] = []
    if metrics.no_travel_mi > 0:
        reasons.append(BLOCKED_NO_TRAVEL)
    if metrics.coverage < min_coverage - 1e-9:
        reasons.append(BLOCKED_INCOMPLETE)
    return Eligibility(not reasons, tuple(reasons))


def rank_key(route: RouteScore) -> tuple[float, float, float, float]:
    """Lexicographic key; rounding only removes floating-point noise (no tolerance bands)."""
    m = route.metrics
    return (
        round(m.severe_mi, 1),
        round(m.high_mi, 1),
        round(m.avg_risk if m.avg_risk is not None else 0.0, 2),
        route.duration_s,
    )


def _name(route_id: str) -> str:
    return f"Route {route_id}"


def _why_not(route: RouteScore) -> str:
    parts = []
    if BLOCKED_NO_TRAVEL in route.eligibility.reasons:
        parts.append(f"No Travel conditions on {route.metrics.no_travel_mi:.0f} mi")
    if BLOCKED_INCOMPLETE in route.eligibility.reasons:
        parts.append(f"forecast covers only {route.metrics.coverage * 100:.1f}% of the route")
    return f"{_name(route.route_id)} is not eligible: " + " and ".join(parts)


def _first_difference(winner: RouteScore, other: RouteScore) -> str:
    w, o = winner.metrics, other.metrics
    name = _name(other.route_id)
    if round(w.severe_mi, 1) != round(o.severe_mi, 1):
        return f"Fewer Severe miles: {w.severe_mi:.0f} vs {o.severe_mi:.0f} on {name}"
    if round(w.high_mi, 1) != round(o.high_mi, 1):
        return f"Fewer High-risk miles: {w.high_mi:.0f} vs {o.high_mi:.0f} on {name}"
    if round(w.avg_risk or 0.0, 2) != round(o.avg_risk or 0.0, 2):
        return f"Lower average risk: {w.avg_risk or 0.0:.2f} vs {o.avg_risk or 0.0:.2f} on {name}"
    return f"Shorter travel time than {name} (same weather risk)"


def _minutes(seconds: float) -> str:
    total = round(seconds / 60)
    hours, mins = divmod(total, 60)
    return f"{hours} h {mins:02d} min" if hours else f"{mins} min"


def recommend(routes: Sequence[RouteScore]) -> Recommendation:
    if not routes:
        raise ValueError("no routes to evaluate")
    eligible = [r for r in routes if r.eligibility.eligible]

    if eligible:
        ranked = sorted(eligible, key=rank_key)  # stable: provider order breaks exact ties
        winner = ranked[0]
        reasons = [_first_difference(winner, other) for other in ranked[1:]]
        reasons += [_why_not(r) for r in routes if not r.eligibility.eligible]
        caveats: list[str] = []
        if winner.metrics.severe_mi > 0:
            caveats.append(f"Still includes {winner.metrics.severe_mi:.0f} mi of Severe risk")
        if winner.metrics.high_mi > 0:
            caveats.append(f"Still includes {winner.metrics.high_mi:.0f} mi of High risk")
        fastest = min(routes, key=lambda r: r.duration_s)
        if fastest.route_id != winner.route_id and winner.duration_s > fastest.duration_s:
            caveats.append(
                f"{_minutes(winner.duration_s - fastest.duration_s)} slower than the fastest route "
                f"({_name(fastest.route_id)})"
            )
        if len(routes) == 1:
            headline = f"{_name(winner.route_id)} is the only available route and is eligible"
        else:
            headline = f"{_name(winner.route_id)} is the safest eligible route"
        return Recommendation(
            RECOMMENDED,
            winner.route_id,
            tuple(r.route_id for r in ranked),
            headline,
            tuple(reasons),
            tuple(caveats),
        )

    reasons_all = tuple(_why_not(r) for r in routes)
    if all(r.metrics.no_travel_mi > 0 for r in routes):
        return Recommendation(NO_SAFE_ROUTE, None, (), "No safe route available", reasons_all, ())
    return Recommendation(
        INCONCLUSIVE, None, (), "A safe recommendation cannot be determined", reasons_all, ()
    )
