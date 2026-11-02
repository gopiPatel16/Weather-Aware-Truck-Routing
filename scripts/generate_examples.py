"""Generate contract examples (REAL planner output with fake routing + mock weather).

Run from the repository root:   backend\\.venv\\Scripts\\python scripts/generate_examples.py
Writes docs/api-examples/*.json - used by the frontend as mock fixtures and by the docs.
Routing and weather are synthetic (clearly labelled demo data); the shapes are exactly the API's.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trucking.errors import ApiError  # noqa: E402
from trucking.planner import Place, PlanInput, Planner  # noqa: E402
from trucking.services.weather.mock import MockWeatherProvider  # noqa: E402
from trucking.tests.fakes import (  # noqa: E402
    CHICAGO,
    DENVER,
    FakeRouting,
    FakeWeather,
    constant_weather,
    three_routes,
)

OUT = ROOT / "docs" / "api-examples"
NOW = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
REQUEST = PlanInput(
    Place("Chicago, IL", *CHICAGO),
    Place("Denver, CO", *DENVER),
    datetime(2026, 11, 2, 6, 0),
    42_000,
    25,
)


def write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    size = (OUT / name).stat().st_size
    print(f"{name:34s} {size / 1024:7.0f} KB")


def summary(plan: dict) -> str:
    rec = plan["recommendation"]
    rows = [
        f"{r['id']}: sev {r['summary']['severe_mi']:.0f} high {r['summary']['high_mi']:.0f} "
        f"NT {r['summary']['no_travel_mi']:.0f} cov {r['summary']['coverage_pct']:.0f}%"
        for r in plan["routes"]
    ]
    return f"  status={rec['status']} route={rec['route_id']} | " + " | ".join(rows)


def main() -> None:
    def planner(weather, routes=None) -> Planner:
        return Planner(FakeRouting(routes), weather, clock=lambda: NOW)

    storm = planner(MockWeatherProvider("plains_storm"))
    plan = storm.plan(REQUEST)
    write("plan_storm.json", plan)
    print(summary(plan))

    calm = planner(MockWeatherProvider("calm")).plan(REQUEST)
    write("plan_calm.json", calm)
    print(summary(calm))

    two = storm.plan(REQUEST)
    two_routes = planner(MockWeatherProvider("plains_storm"), three_routes()[:2]).plan(REQUEST)
    write("plan_two_routes.json", two_routes)
    print(summary(two_routes))

    blocked = planner(constant_weather(wind=60.0)).plan(REQUEST)
    write("plan_no_safe_route.json", blocked)
    print(summary(blocked))

    def half_missing(point, start, hours):
        return None if point[1] < -97 else constant_weather(wind=38.0).builder(point, start, hours)

    inconclusive = planner(FakeWeather(half_missing)).plan(REQUEST)
    write("plan_inconclusive.json", inconclusive)
    print(summary(inconclusive))

    estimated = planner(MockWeatherProvider("calm"), three_routes(guidance=False)).plan(REQUEST)
    write("plan_estimated_eta.json", estimated)
    print(summary(estimated))

    route_a = storm.plan(REQUEST)["routes"][0]
    heat = storm.heatmap(
        [(r["id"], __import__("trucking.domain.polyline", fromlist=["decode"]).decode(r["polyline"])) for r in plan["routes"]],
        datetime.fromisoformat(plan["request"]["departure_utc"].replace("Z", "+00:00")),
        42_000,
    )
    write("heatmap_storm.json", heat)
    print(f"  cells={heat['meta']['cells']} unknown={heat['meta']['unknown_cells']}")
    write("heatmap_request.json", {
        "routes": [{"id": r["id"], "polyline": r["polyline"]} for r in plan["routes"]],
        "departure_utc": plan["request"]["departure_utc"],
        "cargo_weight_lb": 42000,
    })
    write("plan_request.json", {
        "origin": {"label": "Chicago, IL", "lat": CHICAGO[0], "lon": CHICAGO[1]},
        "destination": {"label": "Denver, CO", "lat": DENVER[0], "lon": DENVER[1]},
        "departure_local": "2026-11-02T06:00",
        "cargo_weight_lb": 42000,
        "interval_miles": 25,
    })

    errors = {
        "error_validation.json": ApiError("validation_error", "Some fields are invalid.", 400,
                                          fields={"cargo_weight_lb": ["Ensure this value is greater than or equal to 1."]}),
        "error_invalid_departure.json": ApiError("invalid_departure_time",
                                                  "2026-03-08 02:30 does not exist in America/Chicago (clocks jump forward). The next valid time is 2026-03-08 03:00.", 400),
        "error_routing_unavailable.json": ApiError("routing_unavailable", "The routing service is busy.", 502, retry_after_s=20),
        "error_weather_unavailable.json": ApiError("weather_unavailable", "The weather forecast service is unavailable right now. Please try again shortly.", 502, retry_after_s=30),
        "error_rate_limited.json": ApiError("rate_limited", "Too many requests. Please wait a moment.", 429, retry_after_s=30),
    }
    for name, err in errors.items():
        write(name, err.payload())
    del two, route_a


if __name__ == "__main__":
    main()
