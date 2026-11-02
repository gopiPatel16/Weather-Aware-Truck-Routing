"""HTTP contract: validation, error shape, geocode time zones, heatmap request, OpenAPI."""

from datetime import UTC, datetime

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from trucking import container
from trucking.domain import polyline
from trucking.planner import Planner
from trucking.services.geocoding.base import GeocodeHit
from trucking.services.routing.base import RoutingError
from trucking.tests.fakes import (
    CHICAGO,
    DENVER,
    FakeGeocoder,
    FakeRouting,
    constant_weather,
    three_routes,
)

NOW = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
BODY = {
    "origin": {"label": "Chicago, IL", "lat": CHICAGO[0], "lon": CHICAGO[1]},
    "destination": {"label": "Denver, CO", "lat": DENVER[0], "lon": DENVER[1]},
    "departure_local": "2026-11-02T06:00",
    "cargo_weight_lb": 42000,
    "interval_miles": 25,
}


@pytest.fixture(autouse=True)
def wiring():
    cache.clear()
    container.override(
        Planner(FakeRouting(), constant_weather(), clock=lambda: NOW), FakeGeocoder()
    )
    yield
    container.override(None, None)
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


def test_health(client):
    assert client.get("/api/health/").json() == {"status": "ok"}


def test_plan_returns_the_documented_shape(client):
    response = client.post("/api/plan/", BODY, format="json")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"request", "alternatives", "routes", "recommendation", "meta"}
    route = data["routes"][0]
    assert {
        "id",
        "name",
        "geometry",
        "polyline",
        "segments",
        "summary",
        "eligibility",
        "checkpoints",
        "eta_method",
    } <= set(route)
    assert {
        "coverage_pct",
        "no_travel_mi",
        "severe_mi",
        "high_mi",
        "avg_risk",
        "miles_by_level",
    } <= set(route["summary"])
    cp = route["checkpoints"][3]
    assert {"eta_utc", "tz", "weather", "risk"} <= set(cp) and {"basis", "source_units"} <= set(
        cp["weather"]
    )
    assert data["recommendation"]["status"] == "recommended"


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"cargo_weight_lb": 0}, "cargo_weight_lb"),
        ({"cargo_weight_lb": 999_999}, "cargo_weight_lb"),
        ({"interval_miles": 30}, "interval_miles"),
        ({"departure_local": "tomorrow"}, "departure_local"),
        ({"departure_local": "2026-11-02T06:00:00-06:00"}, "departure_local"),
        ({"origin": {"lat": 95, "lon": 0}}, "origin"),
    ],
)
def test_validation_errors_use_the_error_envelope(client, patch, field):
    response = client.post("/api/plan/", {**BODY, **patch}, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error" and field in error["fields"]


def test_missing_fields_are_reported(client):
    response = client.post("/api/plan/", {}, format="json")
    assert response.status_code == 400 and {"origin", "destination", "cargo_weight_lb"} <= set(
        response.json()["error"]["fields"]
    )


def test_nonexistent_local_departure_is_a_400_with_a_helpful_message(client):
    container.override(
        Planner(
            FakeRouting(), constant_weather(), clock=lambda: datetime(2026, 3, 7, 12, tzinfo=UTC)
        )
    )
    response = client.post(
        "/api/plan/", {**BODY, "departure_local": "2026-03-08T02:30"}, format="json"
    )
    assert response.status_code == 400
    assert (
        response.json()["error"]["code"] == "invalid_departure_time"
        and "does not exist" in response.json()["error"]["message"]
    )


def test_upstream_failures_have_codes_and_retry_hints(client):
    container.override(
        Planner(
            FakeRouting(error=RoutingError("busy", retry_after_s=20)),
            constant_weather(),
            clock=lambda: NOW,
        )
    )
    response = client.post("/api/plan/", BODY, format="json")
    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "routing_unavailable",
        "message": "busy",
        "retry_after_s": 20,
    }


def test_heatmap_roundtrip_uses_the_polyline_from_the_plan(client):
    plan = client.post("/api/plan/", BODY, format="json").json()
    route = plan["routes"][0]
    response = client.post(
        "/api/heatmap/",
        {
            "routes": [{"id": route["id"], "polyline": route["polyline"]}],
            "departure_utc": plan["request"]["departure_utc"],
            "cargo_weight_lb": 42000,
        },
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    assert (
        data["hours"] == 49 and data["cells"] and all(len(c["levels"]) == 49 for c in data["cells"])
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"routes": []},
        {"departure_utc": "2026-11-02T12:00:00"},
        {"departure_utc": "soon"},
        {"routes": [{"id": "A", "polyline": "!!!"}]},
        {"routes": [{"id": "A", "polyline": polyline.encode([(40.0, -90.0)])}]},
    ],
)
def test_heatmap_rejects_bad_requests(client, patch):
    good = {
        "routes": [{"id": "A", "polyline": polyline.encode(three_routes()[0].points[:50])}],
        "departure_utc": "2026-11-02T12:00:00Z",
        "cargo_weight_lb": 40000,
    }
    assert client.post("/api/heatmap/", {**good, **patch}, format="json").status_code == 400


def test_geocode_adds_the_time_zone(client):
    container.override(
        container.get_planner(), FakeGeocoder([GeocodeHit("Denver, CO, USA", 39.7392, -104.9903)])
    )
    data = client.get("/api/geocode/", {"q": "denver"}).json()
    assert data["results"] == [
        {"label": "Denver, CO, USA", "lat": 39.7392, "lon": -104.9903, "timezone": "America/Denver"}
    ]


def test_geocode_needs_a_query(client):
    response = client.get("/api/geocode/", {"q": "d"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "validation_error"


def test_geocode_provider_errors_are_mapped(client):
    class Broken:
        name = "broken"

        def search(self, query, limit=6):
            raise RoutingError("geocoder down")

    container.override(container.get_planner(), Broken())
    assert client.get("/api/geocode/", {"q": "chicago"}).status_code == 502


def test_rate_limit_returns_the_error_envelope(client, settings):
    from rest_framework.settings import api_settings

    api_settings.DEFAULT_THROTTLE_RATES["geocode"] = "2/min"
    try:
        for _ in range(2):
            client.get("/api/geocode/", {"q": "chicago"})
        response = client.get("/api/geocode/", {"q": "chicago"})
        assert response.status_code == 429 and response.json()["error"]["code"] == "rate_limited"
        assert response.json()["error"]["retry_after_s"] > 0
    finally:
        api_settings.DEFAULT_THROTTLE_RATES["geocode"] = "60/min"


def test_openapi_schema_and_docs_are_served(client):
    schema = client.get("/api/schema/")
    assert schema.status_code == 200 and b"/api/plan/" in schema.content
    assert client.get("/api/docs/").status_code == 200
