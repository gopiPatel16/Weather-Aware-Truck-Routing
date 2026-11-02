"""The whole pipeline with fake providers: routes -> checkpoints -> forecast -> risk -> ranking."""

from datetime import UTC, datetime

import pytest

from trucking.domain.forecast import HourlySeries
from trucking.domain.geo import METERS_PER_MILE
from trucking.domain.types import RawRoute
from trucking.errors import ApiError
from trucking.planner import Place, PlanInput, Planner
from trucking.services.routing.base import NoRouteFound, RoutingError
from trucking.services.weather.mock import MockWeatherProvider
from trucking.tests.fakes import (
    CHICAGO,
    DENVER,
    FakeRouting,
    FakeWeather,
    constant_weather,
    curve,
    raw_route,
    three_routes,
)

NOW = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
ORIGIN = Place("Chicago, IL", *CHICAGO)
DEST = Place("Denver, CO", *DENVER)


def request(**kw) -> PlanInput:
    base = {
        "origin": ORIGIN,
        "destination": DEST,
        "departure_local": datetime(2026, 11, 2, 6, 0),
        "cargo_weight_lb": 42_000,
        "interval_miles": 25,
    }
    return PlanInput(**{**base, **kw})


def make(routing=None, weather=None) -> Planner:
    return Planner(routing or FakeRouting(), weather or constant_weather(), clock=lambda: NOW)


def route(plan, route_id):
    return next(r for r in plan["routes"] if r["id"] == route_id)


# ---- happy path ----------------------------------------------------------------------------
def test_three_routes_with_checkpoints_etas_and_full_coverage():
    plan = make().plan(request())
    assert [r["id"] for r in plan["routes"]] == ["A", "B", "C"]
    assert (
        plan["alternatives"]["usable"] == 3
        and "3 valid alternatives" in plan["alternatives"]["message"]
    )
    assert plan["request"]["origin_timezone"] == "America/Chicago"
    assert (
        plan["request"]["departure_utc"] == "2026-11-02T12:00:00Z"
    )  # 06:00 CST read in the ORIGIN zone
    for r in plan["routes"]:
        cps = r["checkpoints"]
        assert cps[0]["mile"] == 0 and cps[-1]["mile"] == pytest.approx(r["distance_mi"], abs=0.1)
        etas = [c["eta_utc"] for c in cps]
        assert etas == sorted(etas) and etas[0] == "2026-11-02T12:00:00Z"
        assert r["summary"]["coverage_pct"] == 100.0 and r["eligibility"]["eligible"]
        assert r["eta_method"] == "route_guidance"
        assert r["polyline"] and r["geometry"]["coordinates"][0] == [
            pytest.approx(-87.63, abs=0.01),
            pytest.approx(41.88, abs=0.01),
        ]
        assert sum(r["summary"]["miles_by_level"].values()) == pytest.approx(
            r["distance_mi"], abs=0.5
        )
    assert (
        plan["recommendation"]["status"] == "recommended"
        and plan["recommendation"]["route_id"] in "ABC"
    )
    # a Chicago -> Denver trip crosses from Central to Mountain time
    zones = [c["tz"] for c in plan["routes"][0]["checkpoints"]]
    assert zones[0] == "America/Chicago" and zones[-1] == "America/Denver"
    assert plan["routes"][0]["arrival_tz"] == "America/Denver"


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoint_count_follows_the_interval(interval):
    plan = make().plan(request(interval_miles=interval))
    r = plan["routes"][0]
    assert abs(r["summary"]["checkpoint_count"] - (r["distance_mi"] / interval + 1)) <= 1.5


def test_segments_cover_the_whole_route_and_merge_equal_levels():
    r = make().plan(request())["routes"][0]
    assert len(r["segments"]) == 1 and r["segments"][0]["level"] == "low"
    assert r["segments"][0]["from_mi"] == 0 and r["segments"][0]["to_mi"] == pytest.approx(
        r["distance_mi"], abs=0.1
    )


def test_weather_is_fetched_once_for_all_routes_with_a_window_covering_the_trip():
    weather = constant_weather()
    make(weather=weather).plan(request())
    assert len(weather.calls) == 1
    _, start, end = weather.calls[0]
    assert (
        start == datetime(2026, 11, 2, 12, tzinfo=UTC) and (end - start).total_seconds() > 16 * 3600
    )


# ---- cargo weight drives the load rules, not the router -----------------------------------
def test_cargo_weight_changes_risk_via_load_rules():
    windy = constant_weather(wind=40.0)  # 35-44 mph
    light = make(weather=windy).plan(request(cargo_weight_lb=35_000))["routes"][0]["summary"]
    heavy = make(weather=windy).plan(request(cargo_weight_lb=45_000))["routes"][0]["summary"]
    assert light["max_level"] == "high" and heavy["max_level"] == "severe"
    plan = make(weather=windy).plan(request(cargo_weight_lb=45_000))
    drivers = plan["routes"][0]["checkpoints"][5]["risk"]["drivers"]
    assert any(d["factor"] == "load_rule" for d in drivers)


def test_routing_provider_never_receives_cargo_weight():
    routing = FakeRouting()
    make(routing=routing).plan(request(cargo_weight_lb=99_999))
    assert len(routing.calls[0]) == 3 and 99_999 not in routing.calls[0]


# ---- recommendation statuses --------------------------------------------------------------
def test_all_routes_blocked_gives_no_safe_route_and_no_recommended_route():
    plan = make(weather=constant_weather(wind=60.0)).plan(request())
    rec = plan["recommendation"]
    assert (
        rec["status"] == "no_safe_route"
        and rec["route_id"] is None
        and rec["headline"] == "No safe route available"
    )
    assert all(
        not r["eligibility"]["eligible"] and r["eligibility"]["reasons"] == ["no_travel"]
        for r in plan["routes"]
    )
    assert all(r["summary"]["no_travel_mi"] > 0 for r in plan["routes"])


def test_missing_weather_is_unknown_and_never_a_recommendation():
    plan = make(
        weather=FakeWeather(lambda p, s, h: None)
    ).plan  # every point fails -> provider error
    with pytest.raises(ApiError) as info:
        plan(request())
    assert info.value.code == "weather_unavailable" and info.value.status == 502


def test_partial_forecast_makes_routes_inconclusive():
    def builder(point, start, hours):
        if point[1] < -95:  # western half has no data
            return None
        return constant_weather().builder(point, start, hours)

    plan = make(weather=FakeWeather(builder)).plan(request())
    rec = plan["recommendation"]
    assert rec["status"] == "inconclusive" and rec["route_id"] is None
    for r in plan["routes"]:
        assert (
            0 < r["summary"]["coverage_pct"] < 100 and r["summary"]["miles_by_level"]["unknown"] > 0
        )
        assert r["summary"]["miles_by_level"]["low"] > 0  # known part is Low ...
        assert r["eligibility"]["reasons"] == ["incomplete_weather"]  # ... but unknown is NOT Low
        unknown = [c for c in r["checkpoints"] if c["risk"]["level"] == "unknown"]
        assert unknown and all(c["weather"] is None and c["risk"]["score"] is None for c in unknown)
    assert any("covers only" in w for w in plan["request"]["warnings"])


def test_blocked_route_is_excluded_and_a_clear_route_recommended():
    clear, blocked = (curve(CHICAGO, DENVER, 0.0), curve(CHICAGO, DENVER, 3.0))

    def builder(point, start, hours):
        wind = 60.0 if point[0] > 42.4 else 10.0  # only the northern bulge is stormy
        return constant_weather(wind=wind).builder(point, start, hours)

    routing = FakeRouting([raw_route(clear, 65, via="I-80"), raw_route(blocked, 70, via="I-90")])
    plan = make(routing=routing, weather=FakeWeather(builder)).plan(request())
    assert (
        route(plan, "B")["summary"]["no_travel_mi"] > 0
        and not route(plan, "B")["eligibility"]["eligible"]
    )
    assert plan["recommendation"]["route_id"] == "A" and plan["recommendation"]["ranking"] == ["A"]


def test_storm_scenario_never_recommends_a_route_with_no_travel_miles():
    plan = make(weather=MockWeatherProvider("plains_storm")).plan(request(interval_miles=10))
    rec = plan["recommendation"]
    assert any(
        r["summary"]["no_travel_mi"] > 0 or r["summary"]["severe_mi"] > 0 for r in plan["routes"]
    )
    if rec["route_id"] is not None:
        assert route(plan, rec["route_id"])["summary"]["no_travel_mi"] == 0
    assert plan["meta"]["weather_model"] == "synthetic demo data"


# ---- alternatives are honest --------------------------------------------------------------
def test_two_routes_returned_are_reported_as_two():
    plan = make(routing=FakeRouting(three_routes()[:2])).plan(request())
    assert len(plan["routes"]) == 2 and "2 valid alternatives" in plan["alternatives"]["message"]


def test_one_route_returned_says_no_alternatives_and_is_not_padded():
    plan = make(routing=FakeRouting(three_routes()[:1])).plan(request())
    assert len(plan["routes"]) == 1 and "only 1 route" in plan["alternatives"]["message"]
    assert (
        plan["recommendation"]["status"] == "recommended"
        and "only available route" in plan["recommendation"]["headline"]
    )


def test_near_duplicate_routes_are_removed_and_reported():
    base = three_routes()[0]
    routes = [base, raw_route(base.points, 62, via="same road")] + three_routes()[1:2]
    plan = make(routing=FakeRouting(routes)).plan(request())
    assert (
        len(plan["routes"]) == 2
        and plan["alternatives"]["returned"] == 3
        and "near-duplicate" in plan["alternatives"]["message"]
    )


def test_no_routes_is_a_422():
    with pytest.raises(ApiError) as info:
        make(routing=FakeRouting([])).plan(request())
    assert (info.value.code, info.value.status) == ("no_route", 422)


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (NoRouteFound("none"), "no_route", 422),
        (RoutingError("timeout", retry_after_s=20), "routing_unavailable", 502),
    ],
)
def test_routing_failures_are_mapped(error, code, status):
    with pytest.raises(ApiError) as info:
        make(routing=FakeRouting(error=error)).plan(request())
    assert (info.value.code, info.value.status) == (code, status)


# ---- ETA fallback is flagged --------------------------------------------------------------
def test_missing_guidance_falls_back_to_estimated_etas_and_says_so():
    plan = make(routing=FakeRouting(three_routes(guidance=False))).plan(request())
    assert all(r["eta_method"] == "estimated_uniform_speed" for r in plan["routes"])
    assert any("estimated from average speed" in w for w in plan["request"]["warnings"])


# ---- departure time ------------------------------------------------------------------------
def test_departure_is_interpreted_in_the_origin_zone_not_the_servers():
    denver_origin = request(origin=DEST, destination=ORIGIN)
    plan = make().plan(denver_origin)
    assert plan["request"]["origin_timezone"] == "America/Denver"
    assert plan["request"]["departure_utc"] == "2026-11-02T13:00:00Z"  # 06:00 MST


def test_nonexistent_local_time_is_rejected():
    planner = Planner(
        FakeRouting(), constant_weather(), clock=lambda: datetime(2026, 3, 7, 12, tzinfo=UTC)
    )
    with pytest.raises(ApiError) as info:
        planner.plan(request(departure_local=datetime(2026, 3, 8, 2, 30)))
    assert info.value.code == "invalid_departure_time" and "does not exist" in info.value.message


def test_ambiguous_local_time_uses_first_occurrence_and_warns():
    planner = Planner(
        FakeRouting(), constant_weather(), clock=lambda: datetime(2026, 10, 31, 12, tzinfo=UTC)
    )
    plan = planner.plan(request(departure_local=datetime(2026, 11, 1, 1, 30)))
    assert plan["request"]["departure_utc"] == "2026-11-01T06:30:00Z"
    assert any("occurs twice" in w for w in plan["request"]["warnings"])


@pytest.mark.parametrize("local", [datetime(2026, 10, 31, 6, 0), datetime(2026, 11, 20, 6, 0)])
def test_departure_outside_the_window_is_rejected(local):
    with pytest.raises(ApiError) as info:
        make().plan(request(departure_local=local))
    assert info.value.code == "invalid_departure_time"


def test_trip_that_is_too_short_is_rejected():
    with pytest.raises(ApiError) as info:
        make().plan(request(destination=Place("Next door", 41.88, -87.64)))
    assert info.value.code == "validation_error"


def test_interval_is_raised_for_very_long_routes():
    miami, seattle = (25.8, -80.2), (47.6, -122.3)
    long_route = RawRoute(
        tuple(curve(miami, seattle, 2.0, n=600)), 3400 * METERS_PER_MILE, 3400 / 60 * 3600
    )
    plan = make(routing=FakeRouting([long_route])).plan(
        request(
            origin=Place("Miami", *miami), destination=Place("Seattle", *seattle), interval_miles=10
        )
    )
    assert plan["request"]["interval_adjusted"] and plan["request"]["interval_miles"] == 25
    assert any("raised from 10 to 25" in w for w in plan["request"]["warnings"])


# ---- heatmap -------------------------------------------------------------------------------
def test_heatmap_cells_have_49_hourly_characters_and_follow_the_load():
    planner = make(weather=constant_weather(wind=40.0))
    points = three_routes()[0].points
    dep = datetime(2026, 11, 2, 12, 20, tzinfo=UTC)
    light = planner.heatmap([("A", points)], dep, 35_000)
    heavy = planner.heatmap([("A", points)], dep, 45_000)
    assert light["hours"] == 49 and light["meta"]["cells"] == len(light["cells"]) > 30
    assert all(len(c["levels"]) == 49 for c in light["cells"])
    assert {ch for c in light["cells"] for ch in c["levels"]} == {"2"}  # High
    assert {ch for c in heavy["cells"] for ch in c["levels"]} == {"3"}  # Severe
    assert light["start_utc"] == "2026-11-02T12:20:00Z"


def test_heatmap_unknown_cells_are_marked_not_low():
    def builder(point, start, hours):
        return None if point[1] < -95 else constant_weather().builder(point, start, hours)

    result = make(weather=FakeWeather(builder)).heatmap(
        [("A", three_routes()[0].points)], datetime(2026, 11, 2, 12, tzinfo=UTC), 40_000
    )
    unknown = [c for c in result["cells"] if c["levels"] == "9" * 49]
    assert unknown and result["meta"]["unknown_cells"] == len(unknown)


def test_heatmap_all_failed_is_a_502():
    with pytest.raises(ApiError) as info:
        make(weather=FakeWeather(lambda p, s, h: None)).heatmap(
            [("A", three_routes()[0].points)], datetime(2026, 11, 2, 12, tzinfo=UTC), 40_000
        )
    assert info.value.status == 502


def test_series_type_used_by_fakes_is_hourly_series():
    sample = constant_weather().builder((41.0, -90.0), datetime(2026, 11, 2, 12, tzinfo=UTC), 5)
    assert isinstance(sample, HourlySeries)
