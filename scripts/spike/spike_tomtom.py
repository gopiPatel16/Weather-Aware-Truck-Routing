"""Disposable API spike #2 - TomTom truck routing + geocoding (needs a free API key).

The "required changes" document asks for proof that:
  * truck mode works and native alternatives return usable routes for long trips,
  * encoded geometry and durations are present, and per-instruction offsets exist for ETAs,
  * vehicleWeight semantics are understood (we deliberately do NOT send cargo weight),
  * the Search API gives typeahead results (and whether a time zone field exists).

Reads TOMTOM_API_KEY from the environment or from backend/.env (never committed).
Run:    python scripts/spike/spike_tomtom.py
Writes: sanitized responses (key removed, big arrays trimmed) to docs/spike/tomtom/*.json
Prints: findings that are copied into docs/spike/SPIKE_REPORT.md
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "spike" / "tomtom"
ROUTING = "https://api.tomtom.com/routing/1/calculateRoute"
SEARCH = "https://api.tomtom.com/search/2/search"
TRIPS = {
    "Chicago-Denver": ((41.8781, -87.6298), (39.7392, -104.9903)),
    "Dallas-Atlanta": ((32.7767, -96.7970), (33.7490, -84.3880)),
    "Minneapolis-Billings": ((44.9778, -93.2650), (45.7833, -108.5007)),
    "Seattle-SaltLakeCity": ((47.6062, -122.3321), (40.7608, -111.8910)),
}


def load_key() -> str:
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    env_file = ROOT / "backend" / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TOMTOM_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("TOMTOM_API_KEY not found (set the env var or add it to backend/.env).")
    return key


def request(url: str, params: list[tuple[str, str]], key: str) -> dict:
    full = url + "?" + urllib.parse.urlencode(params + [("key", key)], safe=",:")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(full, headers={"User-Agent": "truck-routing-spike/0.1"}), timeout=60) as r:
            body, status = r.read(), r.status
    except urllib.error.HTTPError as error:
        body, status = error.read(), error.code
    ms = round((time.perf_counter() - started) * 1000)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = body.decode("utf-8", "replace")
    shown = url + "?" + urllib.parse.urlencode(params, safe=",:")  # key never stored/printed
    return {"url": shown, "status": status, "ms": ms, "bytes": len(body), "data": data}


# --- tiny geometry helpers (spike only) ----------------------------------------------------
def decode_polyline(text: str, precision: int) -> list[tuple[float, float]]:
    factor, index, lat, lon, out = 10**precision, 0, 0, 0, []
    while index < len(text):
        for axis in (0, 1):
            shift = result = 0
            while True:
                byte = ord(text[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        out.append((lat / factor, lon / factor))
    return out


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def length_m(points: list[tuple[float, float]]) -> float:
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def route_points(route: dict) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for leg in route.get("legs", []):
        if "encodedPolyline" in leg:
            pts += decode_polyline(leg["encodedPolyline"], int(leg.get("encodedPolylinePrecision", 5)))
        else:
            pts += [(p["latitude"], p["longitude"]) for p in leg.get("points", [])]
    return pts


def share_ratio(a: list[tuple[float, float]], b: list[tuple[float, float]], within_m: float = 800) -> float:
    """Fraction of route A (sampled every ~2 km) lying within `within_m` of route B."""

    def thin(points: list[tuple[float, float]], step_m: float) -> list[tuple[float, float]]:
        out, last = [points[0]], points[0]
        for p in points[1:]:
            if haversine_m(last, p) >= step_m:
                out.append(p)
                last = p
        return out

    sa, sb = thin(a, 2000), thin(b, 400)
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for p in sb:
        grid.setdefault((int(p[0] * 50), int(p[1] * 50)), []).append(p)
    close = 0
    for p in sa:
        cx, cy = int(p[0] * 50), int(p[1] * 50)
        near = [q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((cx + dx, cy + dy), [])]
        if any(haversine_m(p, q) <= within_m for q in near):
            close += 1
    return close / len(sa)


# --- experiments ---------------------------------------------------------------------------
def trim_route(route: dict) -> dict:
    slim = json.loads(json.dumps(route))
    for leg in slim.get("legs", []):
        if "encodedPolyline" in leg:
            leg["encodedPolyline"] = leg["encodedPolyline"][:120] + f"...[{len(leg['encodedPolyline'])} chars]"
        if "points" in leg:
            leg["points"] = leg["points"][:3] + [f"...[{len(leg['points'])} points]"]
    guidance = slim.get("guidance")
    if guidance and "instructions" in guidance:
        ins = guidance["instructions"]
        guidance["instructions"] = ins[:4] + [f"...[{len(ins)} instructions]"] + ins[-2:]
    return slim


def routing_params(depart_at: str, **extra: str) -> list[tuple[str, str]]:
    params = [
        ("travelMode", "truck"),
        ("routeType", "fastest"),
        ("traffic", "true"),
        ("maxAlternatives", "2"),
        ("departAt", depart_at),
        ("routeRepresentation", "encodedPolyline"),
        ("instructionsType", "coded"),
        ("sectionType", "travelMode"),
        ("sectionType", "motorway"),
        ("report", "effectiveSettings"),
        ("computeTravelTimeFor", "all"),
    ]
    return [(k, v) for k, v in params if k not in extra] + list(extra.items())


def describe_route(i: int, route: dict) -> None:
    summary = route["summary"]
    pts = route_points(route)
    guidance = route.get("guidance", {})
    instructions = guidance.get("instructions", [])
    print(
        f"  route {i}: {summary['lengthInMeters'] / 1609.344:.1f} mi, {summary['travelTimeInSeconds'] / 3600:.2f} h, "
        f"traffic delay {summary.get('trafficDelayInSeconds')} s, legs={len(route.get('legs', []))}, points={len(pts)}, "
        f"polyline length {length_m(pts) / 1609.344:.1f} mi"
    )
    print("    summary keys:", sorted(summary))
    leg = route["legs"][0] if route.get("legs") else {}
    print("    leg keys:", sorted(leg), "| precision:", leg.get("encodedPolylinePrecision"))
    print("    guidance keys:", sorted(guidance), "| instructions:", len(instructions))
    if instructions:
        print("    instruction keys:", sorted(instructions[0]))
        print("    first:", {k: instructions[0].get(k) for k in ("routeOffsetInMeters", "travelTimeInSeconds", "pointIndex", "instructionType")})
        print("    last :", {k: instructions[-1].get(k) for k in ("routeOffsetInMeters", "travelTimeInSeconds", "pointIndex", "instructionType")})
    print("    sections:", sorted({s.get("sectionType") for s in route.get("sections", [])}))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = load_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    depart = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    depart_at = depart.strftime("%Y-%m-%dT%H:%M:%SZ")
    print("departAt:", depart_at)
    routes_by_trip: dict[str, list[dict]] = {}

    for name, (origin, dest) in TRIPS.items():
        path = f"{ROUTING}/{origin[0]},{origin[1]}:{dest[0]},{dest[1]}/json"
        res = request(path, routing_params(depart_at), key)
        print(f"\n=== T1 {name} (truck, maxAlternatives=2) === status={res['status']} {res['ms']} ms {res['bytes']} bytes")
        data = res["data"]
        if res["status"] != 200:
            print("  body:", str(data)[:500])
            continue
        routes = data.get("routes", [])
        routes_by_trip[name] = routes
        print(f"  routes returned: {len(routes)} | formatVersion={data.get('formatVersion')}")
        for i, route in enumerate(routes):
            describe_route(i, route)
        if len(routes) > 1:
            pts = [route_points(r) for r in routes]
            for i in range(len(routes)):
                for j in range(len(routes)):
                    if i != j:
                        print(f"  share of route {i} lying within 800 m of route {j}: {share_ratio(pts[i], pts[j]):.2f}")
        if "report" in data:
            print("  effectiveSettings:", json.dumps(data["report"].get("effectiveSettings"))[:700])
        trimmed = {**data, "routes": [trim_route(r) for r in routes]}
        (OUT_DIR / f"T1_{name}.json").write_text(json.dumps({"url": res["url"], "ms": res["ms"], "response": trimmed}, indent=1), encoding="utf-8")
        time.sleep(0.5)

    # T2/T3: variations on the first trip
    name = "Chicago-Denver"
    origin, dest = TRIPS[name]
    path = f"{ROUTING}/{origin[0]},{origin[1]}:{dest[0]},{dest[1]}/json"
    for label, extra in {
        "T2 vehicleCommercial=true": {"vehicleCommercial": "true"},
        "T3 maxAlternatives=3": {"maxAlternatives": "3"},
        "T4 travelMode=car": {"travelMode": "car"},
    }.items():
        res = request(path, routing_params(depart_at, **extra), key)
        routes = res["data"].get("routes", []) if res["status"] == 200 else []
        print(f"\n=== {label} === status={res['status']} {res['ms']} ms routes={len(routes)}")
        for i, route in enumerate(routes):
            s = route["summary"]
            print(f"  route {i}: {s['lengthInMeters'] / 1609.344:.1f} mi, {s['travelTimeInSeconds'] / 3600:.2f} h")
        if res["status"] != 200:
            print("  body:", str(res["data"])[:400])
        time.sleep(0.5)

    # T5/T6: geocoding typeahead + whether a time-zone field exists
    for query in ("chicago", "1600 pennsylvania", "fargo n"):
        res = request(f"{SEARCH}/{urllib.parse.quote(query)}.json", [("typeahead", "true"), ("limit", "5"), ("countrySet", "US,CA")], key)
        print(f"\n=== T5 search '{query}' === status={res['status']} {res['ms']} ms")
        if res["status"] == 200:
            results = res["data"].get("results", [])
            for r in results[:5]:
                print("  ", r.get("type"), "|", r.get("address", {}).get("freeformAddress"), "|", r.get("position"))
            if results:
                print("  result keys:", sorted(results[0]))
                print("  address keys:", sorted(results[0].get("address", {})))
            (OUT_DIR / f"T5_search_{query.split()[0]}.json").write_text(json.dumps(res["data"], indent=1), encoding="utf-8")
        else:
            print("  body:", str(res["data"])[:300])
        time.sleep(0.3)

    print("\nDone. Responses (key removed) are in", OUT_DIR)


if __name__ == "__main__":
    main()
