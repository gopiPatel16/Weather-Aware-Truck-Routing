"""Eligibility, ranking, coverage and the three recommendation statuses (plan 5.7)."""

import pytest

from trucking.domain.scoring import (
    BLOCKED_INCOMPLETE,
    BLOCKED_NO_TRAVEL,
    INCONCLUSIVE,
    NO_SAFE_ROUTE,
    RECOMMENDED,
    OwnedRisk,
    RouteScore,
    evaluate_eligibility,
    recommend,
    summarize,
)
from trucking.domain.types import RiskLevel

L, M, H, S, N = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


def score(route_id, stretches, duration_s=36_000) -> RouteScore:
    """stretches: [(miles, level-or-None), ...]"""
    metrics = summarize([OwnedRisk(m, lv) for m, lv in stretches])
    return RouteScore(route_id, metrics, evaluate_eligibility(metrics), duration_s)


# ---- metrics ------------------------------------------------------------------------------
def test_miles_by_level_sum_to_total_and_coverage():
    m = summarize(
        [OwnedRisk(10, L), OwnedRisk(20, M), OwnedRisk(5, H), OwnedRisk(5, S), OwnedRisk(10, None)]
    )
    assert sum(m.miles_by_level.values()) == pytest.approx(50)
    assert (m.severe_mi, m.high_mi, m.no_travel_mi) == (5, 5, 0)
    assert m.coverage == pytest.approx(0.8)
    assert m.max_level == S


def test_average_risk_is_distance_weighted_over_known_miles_only():
    m = summarize([OwnedRisk(30, L), OwnedRisk(10, S), OwnedRisk(60, None)])
    assert m.avg_risk == pytest.approx(0.75)  # (30*0 + 10*3) / 40


def test_all_unknown_has_no_average_and_zero_coverage():
    m = summarize([OwnedRisk(50, None)])
    assert m.avg_risk is None and m.coverage == 0.0 and m.max_level is None


# ---- eligibility --------------------------------------------------------------------------
def test_no_travel_makes_a_route_ineligible():
    r = score("A", [(90, L), (10, N)])
    assert not r.eligibility.eligible and r.eligibility.reasons == (BLOCKED_NO_TRAVEL,)


def test_incomplete_weather_makes_a_route_ineligible():
    r = score("A", [(95, L), (5, None)])
    assert r.eligibility.reasons == (BLOCKED_INCOMPLETE,)


def test_both_reasons_can_apply():
    assert score("A", [(80, L), (10, N), (10, None)]).eligibility.reasons == (
        BLOCKED_NO_TRAVEL,
        BLOCKED_INCOMPLETE,
    )


def test_complete_clear_route_is_eligible():
    assert score("A", [(100, L)]).eligibility.eligible


# ---- ranking: strict lexicographic order --------------------------------------------------
def test_fewest_severe_miles_wins_over_everything():
    a = score("A", [(90, L), (10, S)], 30_000)  # fastest but 10 severe miles
    b = score("B", [(100, H)], 90_000)  # slow, lots of High, no Severe
    rec = recommend([a, b])
    assert rec.status == RECOMMENDED and rec.route_id == "B" and rec.ranking == ("B", "A")


def test_high_miles_break_a_severe_tie():
    a = score("A", [(70, L), (30, H)], 30_000)
    b = score("B", [(90, L), (10, H)], 60_000)
    assert recommend([a, b]).route_id == "B"


def test_average_risk_breaks_a_severe_and_high_tie():
    a = score("A", [(50, L), (50, M)], 30_000)  # avg 0.50
    b = score("B", [(80, L), (20, M)], 60_000)  # avg 0.20
    assert recommend([a, b]).route_id == "B"


def test_duration_breaks_a_full_tie():
    a = score("A", [(100, L)], 40_000)
    b = score("B", [(100, L)], 30_000)
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert "Shorter travel time" in rec.reasons[0]


def test_exact_tie_keeps_provider_order():
    a = score("A", [(100, L)], 30_000)
    b = score("B", [(100, L)], 30_000)
    assert recommend([a, b]).route_id == "A"


def test_worked_example_from_the_plan():
    a = score("A", [(875, L), (50, S), (75, H)], 60_000)
    b = score("B", [(900, L), (100, H)], 63_000)
    c = score("C", [(975, L), (25, H)], 68_700)
    rec = recommend([a, b, c])
    assert rec.route_id == "C" and rec.ranking == ("C", "B", "A")
    assert any("2 h 25 min slower" in cv for cv in rec.caveats) or any(
        "slower than the fastest" in cv for cv in rec.caveats
    )


# ---- No Travel and coverage never get recommended -----------------------------------------
def test_a_route_with_no_travel_is_never_recommended_even_if_otherwise_best():
    a = score("A", [(99, L), (1, N)], 10_000)  # best on every other criterion
    b = score("B", [(100, S)], 99_000)
    rec = recommend([a, b])
    assert rec.status == RECOMMENDED and rec.route_id == "B" and rec.ranking == ("B",)
    assert any("Route A is not eligible" in r for r in rec.reasons)


def test_all_routes_blocked_means_no_safe_route_and_no_recommendation():
    rec = recommend([score("A", [(90, L), (10, N)]), score("B", [(50, N), (50, L)])])
    assert rec.status == NO_SAFE_ROUTE and rec.route_id is None and rec.ranking == ()
    assert rec.headline == "No safe route available"


def test_incomplete_weather_everywhere_is_inconclusive_not_a_guess():
    rec = recommend([score("A", [(90, L), (10, None)]), score("B", [(100, None)])])
    assert rec.status == INCONCLUSIVE and rec.route_id is None
    assert "cannot be determined" in rec.headline
    assert any("90.0%" in r for r in rec.reasons)


def test_blocked_plus_incomplete_is_inconclusive():
    rec = recommend([score("A", [(90, L), (10, N)]), score("B", [(90, L), (10, None)])])
    assert rec.status == INCONCLUSIVE


def test_low_coverage_route_cannot_win_by_hiding_its_unknown_miles():
    a = score("A", [(50, L), (50, None)], 20_000)  # looks clean because Unknown is excluded
    b = score("B", [(100, M)], 90_000)
    rec = recommend([a, b])
    assert rec.route_id == "B"


def test_single_eligible_route_is_the_only_available_route():
    rec = recommend([score("A", [(100, L)])])
    assert rec.status == RECOMMENDED and "only available route" in rec.headline


def test_single_blocked_route_gets_no_recommendation():
    assert recommend([score("A", [(100, N)])]).status == NO_SAFE_ROUTE


def test_unknown_is_not_treated_as_low_in_metrics():
    m = summarize([OwnedRisk(50, None)])
    assert m.miles_by_level["low"] == 0 and m.miles_by_level["unknown"] == 50


def test_recommend_requires_routes():
    with pytest.raises(ValueError):
        recommend([])


def test_caveats_never_claim_risk_free():
    rec = recommend([score("A", [(80, L), (20, H)])])
    assert any("High risk" in c for c in rec.caveats)
