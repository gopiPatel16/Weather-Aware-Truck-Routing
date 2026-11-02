"""TomTom routing and geocoding adapters with mocked HTTP (shapes copied from the live spike)."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from trucking.domain.polyline import encode
from trucking.services.geocoding.tomtom import BASE_URL as SEARCH_URL
from trucking.services.geocoding.tomtom import TomTomGeocoder
from trucking.services.routing.base import NoRouteFound, RoutingError, RoutingQuotaExceeded
from trucking.services.routing.tomtom import BASE_URL, TomTomRouting
from trucking.services.weather.cache import DictCache

ORIGIN = (41.8781, -87.6298)
DEST = (39.7392, -104.9903)
DEPART = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
ROUTE_URL = f"{BASE_URL}/41.878100,-87.629800:39.739200,-104.990300/json"

LINE = [(41.8781, -87.6298), (41.5, -90.0), (40.5, -97.0), (39.7392, -104.9903)]


def tomtom_route(length_m=1_653_119, seconds=52_415, *, guidance=True, roads=("I-80 W", "I-76 W")):
    route = {
        "summary": {"lengthInMeters": length_m, "travelTimeInSeconds": seconds},
        "legs": [{"encodedPolyline": encode(LINE), "encodedPolylinePrecision": 5}],
    }
    if guidance:
        route["guidance"] = {
            "instructions": [
                {"routeOffsetInMeters": 0, "travelTimeInSeconds": 0, "street": "S Federal St"},
                {
                    "routeOffsetInMeters": 1_000,
                    "travelTimeInSeconds": 120,
                    "roadNumbers": [roads[0]],
                },
                {
                    "routeOffsetInMeters": 1_500_000,
                    "travelTimeInSeconds": 48_000,
                    "roadNumbers": [roads[1]],
                },
                {"routeOffsetInMeters": length_m, "travelTimeInSeconds": seconds},
            ]
        }
    return route


def router(**kwargs):
    sleeps: list[float] = []
    return TomTomRouting("KEY", http=httpx.Client(), sleep=sleeps.append, **kwargs), sleeps


@respx.mock
def test_requests_native_truck_alternatives_and_never_sends_vehicle_specs():
    route = respx.get(ROUTE_URL).mock(
        return_value=httpx.Response(200, json={"routes": [tomtom_route()]})
    )
    router()[0].get_routes(ORIGIN, DEST, DEPART)
    params = route.calls[0].request.url.params
    assert params["travelMode"] == "truck" and params["routeType"] == "fastest"
    assert params["maxAlternatives"] == "2" and params["traffic"] == "true"
    assert params["departAt"] == "2026-11-02T12:00:00Z"
    assert (
        params["routeRepresentation"] == "encodedPolyline" and params["instructionsType"] == "coded"
    )
    assert params["key"] == "KEY"
    # PLAN D8 / C2: cargo weight is not the vehicle's weight; no vehicle spec is invented.
    for forbidden in (
        "vehicleWeight",
        "vehicleCommercial",
        "vehicleAxleWeight",
        "vehicleLength",
        "vehicleAdrTunnelRestrictionCode",
    ):
        assert forbidden not in params


@respx.mock
def test_parses_geometry_distance_duration_guidance_and_via():
    respx.get(ROUTE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "routes": [
                    tomtom_route(),
                    tomtom_route(1_900_000, 61_000, roads=("I-70 W", "I-70 W")),
                ]
            },
        )
    )
    result = router()[0].get_routes(ORIGIN, DEST, DEPART)
    assert result.requested == 3 and len(result.routes) == 2  # exactly what the provider returned
    first = result.routes[0]
    assert len(first.points) == len(LINE) and first.points[0] == pytest.approx(LINE[0], abs=1e-5)
    assert first.distance_m == 1_653_119 and first.duration_s == 52_415
    assert first.time_offsets[0] == (0.0, 0.0) and first.time_offsets[-1] == (1_653_119.0, 52_415.0)
    assert first.via == "I-80 W"  # the road number carrying most of the distance
    assert result.routes[1].via == "I-70 W"


@respx.mock
def test_missing_guidance_gives_empty_offsets_so_the_planner_flags_an_estimate():
    respx.get(ROUTE_URL).mock(
        return_value=httpx.Response(200, json={"routes": [tomtom_route(guidance=False)]})
    )
    route = router()[0].get_routes(ORIGIN, DEST, DEPART).routes[0]
    assert route.time_offsets == () and route.via is None


@respx.mock
def test_routes_with_missing_geometry_length_or_duration_are_discarded():
    bad = [
        {"summary": {"lengthInMeters": 1000, "travelTimeInSeconds": 60}, "legs": []},
        {"summary": {"travelTimeInSeconds": 60}, "legs": [{"encodedPolyline": encode(LINE)}]},
        {
            "summary": {"lengthInMeters": 5000, "travelTimeInSeconds": 0},
            "legs": [{"encodedPolyline": encode(LINE)}],
        },
    ]
    respx.get(ROUTE_URL).mock(
        return_value=httpx.Response(200, json={"routes": [*bad, tomtom_route()]})
    )
    assert len(router()[0].get_routes(ORIGIN, DEST, DEPART).routes) == 1


@respx.mock
def test_no_usable_routes_is_no_route():
    respx.get(ROUTE_URL).mock(return_value=httpx.Response(200, json={"routes": []}))
    with pytest.raises(NoRouteFound):
        router()[0].get_routes(ORIGIN, DEST, DEPART)


@respx.mock
def test_http_400_is_no_route_with_the_provider_message():
    respx.get(ROUTE_URL).mock(
        return_value=httpx.Response(400, json={"detailedError": {"message": "Cannot match origin"}})
    )
    with pytest.raises(NoRouteFound, match="Cannot match origin"):
        router()[0].get_routes(ORIGIN, DEST, DEPART)


@respx.mock
def test_rejected_key_is_a_routing_error_without_leaking_the_key():
    respx.get(ROUTE_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(RoutingError) as info:
        router()[0].get_routes(ORIGIN, DEST, DEPART)
    assert "KEY" not in info.value.message


@respx.mock
def test_rate_limit_maps_to_quota_with_retry_after():
    respx.get(ROUTE_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "45"}))
    with pytest.raises(RoutingQuotaExceeded) as info:
        router()[0].get_routes(ORIGIN, DEST, DEPART)
    assert info.value.retry_after_s == 45 and info.value.status == 503


@respx.mock
def test_server_errors_are_retried_then_reported_with_retry_after():
    route = respx.get(ROUTE_URL).mock(return_value=httpx.Response(503))
    r, sleeps = router()
    with pytest.raises(RoutingError) as info:
        r.get_routes(ORIGIN, DEST, DEPART)
    assert route.call_count == 3 and sleeps == [0.5, 1.0]
    assert info.value.retry_after_s == 20 and info.value.status == 502


@respx.mock
def test_recovers_after_a_transient_failure():
    respx.get(ROUTE_URL).mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json={"routes": [tomtom_route()]})]
    )
    assert len(router()[0].get_routes(ORIGIN, DEST, DEPART).routes) == 1


@respx.mock
def test_timeouts_are_retried_and_reported():
    route = respx.get(ROUTE_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(RoutingError):
        router()[0].get_routes(ORIGIN, DEST, DEPART)
    assert route.call_count == 3


@respx.mock
def test_invalid_json_is_a_routing_error():
    respx.get(ROUTE_URL).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(RoutingError):
        router()[0].get_routes(ORIGIN, DEST, DEPART)


@respx.mock
def test_identical_requests_in_the_same_departure_hour_hit_the_cache():
    route = respx.get(ROUTE_URL).mock(
        return_value=httpx.Response(200, json={"routes": [tomtom_route()]})
    )
    r, _ = router(cache=DictCache())
    r.get_routes(ORIGIN, DEST, DEPART)
    r.get_routes(ORIGIN, DEST, DEPART.replace(minute=40))
    assert route.call_count == 1
    r.get_routes(ORIGIN, DEST, DEPART.replace(hour=13))
    assert route.call_count == 2


# ---- geocoder -----------------------------------------------------------------------------------
SEARCH = {
    "results": [
        {
            "address": {"freeformAddress": "Chicago, IL", "countryCode": "US"},
            "position": {"lat": 41.883229, "lon": -87.632398},
        },
        {
            "address": {"freeformAddress": "Chicago, IL", "countryCode": "US"},
            "position": {"lat": 41.9, "lon": -87.6},
        },
        {
            "address": {"freeformAddress": "West Chicago, IL", "countryCode": "US"},
            "position": {"lat": 41.88, "lon": -88.2},
        },
        {"address": {"freeformAddress": "No position"}},
    ]
}


@respx.mock
def test_geocoder_parameters_and_parsing_drop_duplicates_and_broken_items():
    route = respx.get(f"{SEARCH_URL}/chicago.json").mock(
        return_value=httpx.Response(200, json=SEARCH)
    )
    hits = TomTomGeocoder("KEY", http=httpx.Client()).search("  chicago ", limit=5)
    params = route.calls[0].request.url.params
    assert (
        params["typeahead"] == "true" and params["limit"] == "5" and params["countrySet"] == "US,CA"
    )
    assert [h.label for h in hits] == ["Chicago, IL, US", "West Chicago, IL, US"]
    assert hits[0].lat == pytest.approx(41.883229)


@respx.mock
def test_geocoder_url_encodes_the_query_and_caches():
    route = respx.get(f"{SEARCH_URL}/1600%20penn%2Fav.json").mock(
        return_value=httpx.Response(200, json=SEARCH)
    )
    g = TomTomGeocoder("KEY", http=httpx.Client(), cache=DictCache())
    g.search("1600 penn/av")
    g.search("1600 penn/av")
    assert route.call_count == 1


@respx.mock
def test_geocoder_errors_map_to_routing_errors():
    respx.get(f"{SEARCH_URL}/x.json").mock(return_value=httpx.Response(429))
    with pytest.raises(RoutingQuotaExceeded):
        TomTomGeocoder("KEY", http=httpx.Client()).search("x")
    respx.get(f"{SEARCH_URL}/y.json").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(RoutingError):
        TomTomGeocoder("KEY", http=httpx.Client(), sleep=lambda _s: None).search("y")
