# API spike report

Evidence gathered **before** building the provider code, as required by the review document (section 5).
Raw sanitized responses are in `docs/spike/open-meteo/` and `docs/spike/tomtom/` (both live; keys removed).
Scripts: `scripts/spike/spike_open_meteo.py`, `scripts/spike/spike_tomtom.py`.

## Status

| Provider / feature | Verified by | Status |
|---|---|---|
| Open-Meteo multi-point forecast, units, timestamps, horizon | **Live run, 1 Nov 2026** (below) | ✅ proven |
| Open-Meteo precipitation timing | Open-Meteo docs + `precipitation = rain + showers + snowfall/7` check on live data | ✅ rule in `docs/PLAN.md` §5.4, tests in `test_forecast_select.py` |
| Open-Meteo usage and licence | Open-Meteo terms page | ✅ checked |
| TomTom truck routing, alternatives, encoded geometry | **Live run, 2 Nov 2026** (section 2) | ✅ proven |
| TomTom ETA data (`guidance.instructions[]`) | **Live run, 2 Nov 2026** | ✅ proven (offsets and times present on every route, alternatives included) |
| TomTom `vehicleWeight` semantics | TomTom documentation | ✅ decision: never sent |
| TomTom Search / geocoding | **Live run, 2 Nov 2026** | ✅ proven; no time-zone field, so zones are computed offline |
| Hosting (Render free) | Render documentation | ⏳ verify after deploy |

**Rule (met):** TomTom-dependent code was written only after `scripts/spike/spike_tomtom.py` had run against the live API and its output had been reviewed.

---

## 1. Open-Meteo (live)

Request shape used by the app: `latitude=…,…&longitude=…,…&hourly=wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,temperature_2m&wind_speed_unit=mph&precipitation_unit=inch&temperature_unit=fahrenheit&timezone=GMT&start_hour=…&end_hour=…`

| # | Experiment | Result |
|---|---|---|
| E1 | defaults, 3 points | units **km/h, mm, cm (snowfall), °C**. Response is a JSON **list** in request order |
| E2 | requested imperial units | `hourly_units`: wind **`mp/h`** (not `mph`), rain / showers / precipitation / **snowfall `inch`**, temperature `°F`. 51 stamps for a +50 h window, 0 nulls |
| E3 | `timezone=auto` | per-location IANA names (`America/Chicago`, `America/Denver`) but abbreviations like `GMT-6` → labels are computed locally with `zoneinfo`; app uses `timezone=GMT` (`utc_offset_seconds` = 0) |
| E4 | 100 locations, one request | HTTP 200 in **1.6 s**, 344 KB JSON (51 h × 7 variables), URL 1.6 KB, 0 nulls. Returned coordinates are **grid-snapped** (41.88 → 41.8795, −87.63 → −87.6497) → results matched by **order**, not by returned coordinates |
| E5 | `end_hour` beyond the horizon | **HTTP 400** `Parameter 'end_hour' is out of allowed range from 2026-07-31 to 2026-11-16` (today + 15 days) → client clamps and treats later hours as Unknown |
| E6 | `start_hour` 3 h in the past | accepted, values present (needed when departure is "now") |
| — | single location | response is a **dict**, not a list → the parser handles both |
| — | accumulation check | over the whole window `max |precipitation − (rain + showers + snowfall/7)| = 0.0` → `precipitation` also contains snow water-equivalent, so rain is `rain + showers` |

**Findings that changed the code**
1. The unit guard accepts `"mp/h"`; an unknown unit string raises (never guessed). Snowfall's unit is read per response (`cm` → ÷2.54, `inch` → ×1); it is not inferred from `precipitation_unit`.
2. Rain = `rain + showers` (both liquid; `precipitation` would double-count snow).
3. Precipitation values are sums over the **preceding** hour; wind is instantaneous. The interval-matching rule is in `docs/PLAN.md` §5.4 and `trucking/domain/forecast.py` (no "nearest hour").

**Usage and licence** (open-meteo.com/en/terms): free API is for **non-commercial** use (no ads/subscriptions; donations allowed); data under **CC BY 4.0** → attribution "Weather data by Open-Meteo.com" is shown in the UI and README; limits <10 000 calls/day, 5 000/h, 600/min applied **per IP / application** — shared hosts such as Render may hit them sooner, so responses are cached 30 min, 429 is retried with back-off, and failures degrade to Unknown (never Low). Commercial use would require a paid plan (`OPEN_METEO_API_KEY` is supported).

## 2. TomTom (documentation verified, then proven live on 2 Nov 2026)

From the official docs (docs.tomtom.com, Calculate Route + Guidance Instructions):
- `travelMode=truck` is supported; `maxAlternatives` 0–5 ("fewer routes may be returned if fewer exist").
- `routeRepresentation=encodedPolyline`: `legs[].encodedPolyline` with `encodedPolylinePrecision` 5 (7 with `coordinatePrecision=full`).
- `instructionsType=coded|text|tagged` adds `guidance.instructions[]` with `routeOffsetInMeters` and `travelTimeInSeconds` (distance and time from the route start), `pointIndex`, `roadNumbers`, `street`, `stateCode`; "instructions will be generated for each route returned" (alternatives included).
- `departAt` RFC 3339; if no offset the origin's zone is assumed; `traffic=true` by default.
- `vehicleWeight`: "Weight of the vehicle in kilograms" — the vehicle, **not the cargo**. **Decision: not sent.** Axle count, dimensions and hazmat are not sent either. `vehicleCommercial` is sent only if live test T2 shows it matters (then disclosed in the README).
- Not documented: a maximum route length; a compute limit of about 30 s exists, and `maxAlternatives > 0` and long distances slow responses → request timeout is generous and failures are reported honestly.

## 2.1 Live results (`scripts/spike/spike_tomtom.py`, responses in `docs/spike/tomtom/`)

| Question | Result |
|---|---|
| Does truck mode return alternatives on ~1000-mile trips? | **Yes.** `maxAlternatives=2` returned **3 routes on all four trips**: Chicago→Denver 1027 / 1190 / 1325 mi; Dallas→Atlanta 784 / 834 / 966 mi; Minneapolis→Billings 843 / 946 / 1327 mi; Seattle→Salt Lake City 843 / 1001 / 1051 mi. Responses took 3.9–5.6 s |
| Are `guidance.instructions[]` offsets present for truck mode and for alternatives? | **Yes**, on every route: `routeOffsetInMeters` and `travelTimeInSeconds` from the first instruction (0, 0) to the arrival instruction (offset = route length). ETA therefore comes from route guidance (`eta_method = route_guidance`); the uniform-speed fallback was not needed |
| Polyline precision? | `encodedPolylinePrecision: 5` on every leg; one leg per route |
| Do the duplicate thresholds separate real alternatives? | Yes. Within 800 m, the share of one route lying on another was 0.00–0.22 for the pairs printed (Minneapolis→Billings and Seattle→Salt Lake City), far below the 0.95 duplicate threshold, so provider alternatives are genuinely different roads |
| `vehicleCommercial=true` (T2)? | Returned the same three routes as the default truck request (1027 / 1190 / 1325 mi), i.e. no measurable effect on this trip. **Not sent** (plan D8): the app makes no vehicle assumptions beyond `travelMode=truck` |
| `maxAlternatives=3` (T3)? | Returns 4 routes but takes 10.5 s; the app asks for 2 alternatives and shows what it gets |
| `travelMode=car` (T4)? | Car mode returned 1027 / 1190 / 1238 mi — the third route differs from truck mode (1325 mi), confirming truck mode changes routing |
| Search typeahead (T5)? | Works for cities and street addresses (`typeahead=true`, `countrySet=US,CA`, 0.6–1.6 s). Result fields: `address.freeformAddress`, `position`, `type`, `entityType`. **No time-zone field**, so the backend derives IANA zones from coordinates offline |
| Traffic delay in the sample? | 0 s (the departure was in the future); durations are typical-traffic estimates |

**Environment note.** On this development PC Python rejected TomTom's certificate (`self-signed certificate in certificate chain`) because a TLS-intercepting layer re-signs HTTPS traffic. Certificate verification was *not* disabled; the spike was run with the operating system's trust store (`truststore`). The backend has the same switch: `USE_SYSTEM_CA_STORE=1`.

**To re-run:** put `TOMTOM_API_KEY=…` in `backend/.env`, then `backend\.venv\Scripts\python scripts\spike\spike_tomtom.py` (add `USE_SYSTEM_CA_STORE`-style trust-store handling if your network intercepts TLS).
