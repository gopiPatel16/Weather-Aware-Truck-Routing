"""Disposable API spike #1 - Open-Meteo multi-point hourly forecast.

The "required changes" document asks for evidence before the full build: what does Open-Meteo
*actually* return (field names, units, timestamps, accumulation semantics, horizon behaviour)?

Run:    python scripts/spike/spike_open_meteo.py
Writes: sanitized sample responses to docs/spike/open-meteo/*.json (no API key is used or stored)
Prints: a findings summary that is copied into docs/spike/SPIKE_REPORT.md
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://api.open-meteo.com/v1/forecast"
OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "spike" / "open-meteo"
HOURLY = [
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "precipitation",
    "temperature_2m",
]
CITIES = {
    "Chicago": (41.8781, -87.6298),
    "Omaha": (41.2565, -95.9345),
    "Denver": (39.7392, -104.9903),
}
STAMP = "%Y-%m-%dT%H:%M"


def fetch(params: dict[str, str]) -> dict:
    url = BASE_URL + "?" + urllib.parse.urlencode(params, safe=",:")
    request = urllib.request.Request(url, headers={"User-Agent": "truck-routing-spike/0.1"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body, status = response.read(), response.status
    except urllib.error.HTTPError as error:
        body, status = error.read(), error.code
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = body.decode("utf-8", "replace")
    return {"url": url, "status": status, "ms": elapsed_ms, "bytes": len(body), "data": data}


def locations(data: object) -> list[dict]:
    if isinstance(data, list):
        return data
    return [data] if isinstance(data, dict) else []


def null_counts(hourly: dict) -> dict[str, int]:
    return {k: sum(v is None for v in vals) for k, vals in hourly.items() if k != "time"}


def save(name: str, payload: object) -> None:
    (OUT_DIR / f"{name}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")


def describe(label: str, result: dict) -> None:
    print(f"\n=== {label} ===")
    print(f"status={result['status']}  {result['ms']} ms  {result['bytes']} bytes")
    locs = locations(result["data"])
    if result["status"] != 200 or not locs or "hourly" not in locs[0]:
        print("body:", str(result["data"])[:400])
        return
    first = locs[0]
    hourly = first["hourly"]
    print(f"locations returned: {len(locs)}  (top-level type: {type(result['data']).__name__})")
    print("keys:", sorted(k for k in first if k not in ("hourly", "hourly_units")))
    print("hourly_units:", first["hourly_units"])
    print(f"time[0]={hourly['time'][0]}  time[-1]={hourly['time'][-1]}  n={len(hourly['time'])}")
    print("null counts (first location):", null_counts(hourly))
    row = {k: v[:3] for k, v in hourly.items()}
    print("first 3 hours:", json.dumps(row))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start, end = now, now + timedelta(hours=50)
    lats = ",".join(str(lat) for lat, _ in CITIES.values())
    lons = ",".join(str(lon) for _, lon in CITIES.values())
    window = {"start_hour": start.strftime(STAMP), "end_hour": end.strftime(STAMP)}
    base = {"latitude": lats, "longitude": lons, "hourly": ",".join(HOURLY), **window}
    wanted = {
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
    }
    print(f"spike run at {datetime.now(timezone.utc).isoformat()}  window {start.strftime(STAMP)} -> {end.strftime(STAMP)}")

    # E1: provider defaults (shows which units come back when we ask for nothing special)
    e1 = fetch(base)
    describe("E1 defaults (km/h, mm, cm, C)", e1)
    save("E1_default_units", e1)
    time.sleep(0.4)

    # E2: the request the app will make (mph / inch / fahrenheit / GMT)
    e2 = fetch({**base, **wanted})
    describe("E2 requested mph / inch / fahrenheit / GMT", e2)
    save("E2_requested_units", e2)
    time.sleep(0.4)

    # E3: timezone=auto to see the per-location time zone fields
    e3 = fetch({**base, **wanted, "timezone": "auto"})
    describe("E3 timezone=auto", e3)
    for loc in locations(e3["data"]):
        print("  tz:", loc.get("timezone"), loc.get("timezone_abbreviation"), "offset", loc.get("utc_offset_seconds"))
    save("E3_timezone_auto", e3)
    time.sleep(0.4)

    # E4: 100 locations along Chicago -> Denver in one request
    n = 100
    pts = [
        (
            round(41.8781 + (39.7392 - 41.8781) * i / (n - 1), 2),
            round(-87.6298 + (-104.9903 + 87.6298) * i / (n - 1), 2),
        )
        for i in range(n)
    ]
    e4 = fetch(
        {
            **base,
            **wanted,
            "latitude": ",".join(str(p[0]) for p in pts),
            "longitude": ",".join(str(p[1]) for p in pts),
        }
    )
    describe("E4 100 locations in one request", e4)
    locs4 = locations(e4["data"])
    print(f"  url length: {len(e4['url'])} chars; locations: {len(locs4)}")
    if locs4 and "hourly" in locs4[0]:
        print("  null counts (all locations):", sum(sum(null_counts(l['hourly']).values()) for l in locs4))
        print("  returned lat/lon of first 3 (grid snapping):", [(l['latitude'], l['longitude']) for l in locs4[:3]])
    save(
        "E4_100_locations_trimmed",
        {
            "url_length": len(e4["url"]),
            "status": e4["status"],
            "ms": e4["ms"],
            "bytes": e4["bytes"],
            "locations": len(locs4),
            "first": locs4[0] if locs4 else None,
            "last": locs4[-1] if locs4 else None,
        },
    )
    time.sleep(0.4)

    # E5: beyond the 16-day horizon
    far_end = (now + timedelta(days=17)).strftime(STAMP)
    e5 = fetch({**base, **wanted, "start_hour": (now + timedelta(days=15)).strftime(STAMP), "end_hour": far_end})
    describe("E5 window crossing the 16-day horizon", e5)
    save("E5_beyond_horizon", {k: e5[k] for k in ("url", "status", "ms")} | {"body_head": str(e5["data"])[:600]})
    time.sleep(0.4)

    # E6: hours already in the past (departure 'now' needs the current hour)
    e6 = fetch(
        {
            **base,
            **wanted,
            "latitude": str(CITIES["Chicago"][0]),
            "longitude": str(CITIES["Chicago"][1]),
            "start_hour": (now - timedelta(hours=3)).strftime(STAMP),
            "end_hour": (now + timedelta(hours=2)).strftime(STAMP),
        }
    )
    describe("E6 start_hour 3 h in the past", e6)
    save("E6_past_hours", e6)

    # Findings -------------------------------------------------------------------------
    print("\n=== FINDINGS ===")
    u1 = locations(e1["data"])[0]["hourly_units"] if e1["status"] == 200 else {}
    u2 = locations(e2["data"])[0]["hourly_units"] if e2["status"] == 200 else {}
    print("default units :", u1)
    print("requested     :", u2)
    print("snowfall unit default -> with precipitation_unit=inch :", u1.get("snowfall"), "->", u2.get("snowfall"))
    if e2["status"] == 200:
        loc = locations(e2["data"])[0]
        print("utc_offset_seconds with timezone=GMT:", loc.get("utc_offset_seconds"), "| timezone:", loc.get("timezone"))
        biggest = 0.0
        for loc in locations(e2["data"]):
            h = loc["hourly"]
            for i in range(len(h["time"])):
                parts = [h["rain"][i], h["showers"][i], h["snowfall"][i], h["precipitation"][i]]
                if None in parts:
                    continue
                rain_like = h["rain"][i] + h["showers"][i] + h["snowfall"][i] / 7
                biggest = max(biggest, abs(h["precipitation"][i] - rain_like))
        print("max |precipitation - (rain + showers + snowfall/7)| over the window:", round(biggest, 4), "inch")
        peak = {k: max((v for v in vals if v is not None), default=None) for k, vals in locations(e2["data"])[0]["hourly"].items() if k != "time"}
        print("peak values at first location in window:", peak)


if __name__ == "__main__":
    main()
