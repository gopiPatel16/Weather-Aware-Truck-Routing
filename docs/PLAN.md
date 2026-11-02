# Weather-Aware Truck Routing — Revised Plan (v2)

> **Status.** v2 incorporates every correction in *Weather-Aware Truck Routing — Required Changes* (PDF, 1 Nov 2026).
> §2 holds the API-spike evidence and the **GO / NO-GO** status. Numbers for latency, frame rate, Lighthouse and heatmap cell counts are **targets to be measured** (§11), not facts.
> This file is the single source of truth; it is copied to `docs/PLAN.md` in the repo.

## 0. What changed from v1

| PDF § | Correction | Handled in |
|---|---|---|
| 4.1 | **No Travel is a hard eligibility exclusion**, not a ranking tier. Eligible routes are ranked only by (Severe mi, High mi, avg risk, duration). All blocked → "No safe route available", nothing labelled Recommended. No eligible route because weather is incomplete → "a safe recommendation cannot be determined" | §5.7 |
| 4.2 | Cargo weight is **never** sent to TomTom `vehicleWeight`; no invented truck specifications | §5.1, D8 |
| 4.3 | Units normalised to mph and in/hr after checking the **returned** unit metadata; rain+showers rule documented; snowfall unit inspected, never assumed | §5.3 |
| 4.4 | ETA from route travel-time data; forecast interval that **covers** the ETA (no "nearest hour"); documented between-hours policy + conservative adjacent-interval check; fallback flagged "estimated" | §5.4 |
| 4.5 | Departure is read in the **origin's** time zone; UTC internally; per-checkpoint zone labels; DST ambiguous/nonexistent times handled and tested | §5.5 |
| 4.6 | Only provider-returned truck alternatives; **no circle-waypoint fill-in**; honest "N valid alternatives" message | §5.1 |
| 4.7 | Unknown ≠ Low; coverage % per route; **complete coverage required** for a definitive recommendation | §5.3, §5.7 |
| 4.8 | Hybrid display: smooth overview + exact checkpoint markers + risk-coloured route segments; grid in **real miles** (not 0.25°); data preloaded for 0–48 h | §6 |
| 5 | Real API spike before the full build | §2, `docs/spike/` |
| 6 | Deferred: OSRM/Photon fallback, waypoint route generation, Zustand/TanStack Query, instrumentation-first. Versions pinned only after a compatibility check. No keep-alive dependency | §4, §12 |
| 7–9 | Test matrix, acceptance checklist, traceability | §10, §15, §16 |

---

## 1. Scope (unchanged from the assignment)

A React + Django app for a truck driver choosing a safer route from weather, **cargo weight** and travel time.

- **Inputs:** origin & destination · departure date/time · cargo/load weight (lb) · sampling interval 10 / 25 / 50 mi.
- **Behaviour:** up to **three genuine** truck-route options from a routing API · weather sampled every N miles using the truck's ETA at each checkpoint · risk from the exact thresholds + load rules · recommend the safest **eligible** route balancing risk and time · all routes, checkpoints, risk levels, ETAs and summaries on a map · weather heatmap along the corridor with a 0–48 h slider.
- **Deliverables:** GitHub repo · hosted app · 5–10 min Loom. **Grading:** 40 % routing/weather/risk/recommendation · 40 % UI/map/heatmap · 15 % code quality · 5 % docs + walkthrough. *Correctness and clarity over extra features.*

---

## 2. API spike evidence and GO / NO-GO

### 2.1 Evidence (full detail in `docs/spike/SPIKE_REPORT.md`)

| Item | How verified | Result | Status |
|---|---|---|---|
| Open-Meteo multi-point forecast | **Live**: `scripts/spike/spike_open_meteo.py` (E1–E6), responses in `docs/spike/open-meteo/` | 3-point and 100-point requests return a **list** in request order (a single point returns a **dict**). Returned lat/lon are **grid-snapped** (41.88 → 41.8795) so results are matched by *order*. 100 locations: 1.6 s, 344 KB, URL 1.6 KB. Hourly fields present, 0 nulls in the sampled window | ✅ proven |
| Units | Live E1/E2 | Defaults km/h · mm · **cm** · °C. With `wind_speed_unit=mph&precipitation_unit=inch&temperature_unit=fahrenheit`: unit strings are **`mp/h`**, `inch` (rain, showers, precipitation **and snowfall**), `°F`. The guard must therefore accept `mp/h` — a naïve `== "mph"` check would fail | ✅ proven |
| Timestamps / time zone | Live E2/E3 | `time` = `YYYY-MM-DDTHH:MM`, no offset; `timezone=GMT` → `utc_offset_seconds: 0`. `timezone=auto` gives IANA names but abbreviations like `GMT-6`, so labels are computed locally from `zoneinfo` | ✅ proven |
| Window / horizon | Live E5/E6 | `start_hour`/`end_hour` work (51 stamps for +50 h). Past hours accepted. `end_hour` beyond today+15 days → **HTTP 400** `"Parameter 'end_hour' is out of allowed range from 2026-07-31 to 2026-11-16"` → client clamps and treats later hours as missing | ✅ proven |
| Precipitation timing | Open-Meteo docs + fixture | `rain`, `showers`, `snowfall`, `precipitation` are sums over the **preceding hour**; `wind_speed_10m` is instantaneous at the stamp. In the sampled window `precipitation = rain + showers + snowfall/7` (max diff 0.0) | ✅ rule written (§5.4) + fixture |
| Usage and licence | Open-Meteo terms page | Free API is **non-commercial** (no ads/subscriptions; donations allowed); data under **CC BY 4.0**; <10 000 calls/day, 5 000/h, 600/min, applied **per IP / application** — shared hosts such as Render "may hit limits sooner". Our use: non-profit demo → permitted. Attribution "Weather data by Open-Meteo.com" in UI + README. Commercial use → paid plan | ✅ checked |
| TomTom truck routing | **Docs verified**; live run pending key | `travelMode=truck`; `maxAlternatives` 0–5 ("fewer routes may be returned"); `routeRepresentation=encodedPolyline` with `encodedPolylinePrecision` 5 (7 with `coordinatePrecision=full`); `departAt` RFC 3339, `traffic=true` default | ⏳ **needs live run** |
| TomTom ETA data | Docs verified; live run pending | `instructionsType=coded|text|tagged` adds `guidance.instructions[]` with `routeOffsetInMeters`, `travelTimeInSeconds`, `pointIndex`, `roadNumbers`, `street`, `stateCode`; generated **for each returned route** incl. alternatives | ⏳ needs live run |
| TomTom weight semantics | Docs verified | `vehicleWeight`: "weight of the vehicle in kilograms"; non-zero ⇒ weight restrictions considered. **Not cargo weight** → we do not send it | ✅ decision |
| TomTom Search | Docs/search | Free tier 2 500 non-tile requests/day, no credit card | ⏳ live run |
| Hosting (Render free) | Render docs | Spins down after 15 min idle; wake ≈ 1 min; 750 free instance-hours/month; ephemeral filesystem; bandwidth quota; secrets via env vars | ⏳ verify after deploy (M7) |

### 2.2 GO / NO-GO

| Area | Status | Reason |
|---|---|---|
| Domain logic (risk, eligibility, ETA, forecast-interval policy, time zones, checkpoints, heatmap grid) | **GO** | no provider dependency; fully specified below |
| Open-Meteo client | **GO** | evidence above |
| Backend skeleton, planner, API (with fake routing provider in tests) | **GO** | provider-independent contract |
| Frontend (against the contract in §7 and fixtures) | **GO** | independent of provider data |
| **TomTom adapter + live-trip tests** | **HOLD** | needs `scripts/spike/spike_tomtom.py` run with the user's free key. Rule: no TomTom-dependent code is called *done* until that output is reviewed. If guidance offsets are absent → documented fallback (uniform-speed ETA, flagged "estimated"); if alternatives are scarce → show what is returned (§5.1) |
| Deployment | after M2–M6 | |

---

## 3. Decisions

| # | Decision | Value |
|---|---|---|
| D1 | Routing + geocoding | **TomTom** (truck mode; free key, no card). OSRM/Photon fallback **deferred** |
| D2 | Sampling interval | user chooses **10 / 25 / 50 mi** (default 25); engine takes any N |
| D3 | Wind used | **sustained** 10 m speed; gusts shown for information only |
| D4 | Band boundaries | PDF §3 convention — see §5.6 |
| D5 | Eligibility vs ranking | No Travel miles ⇒ ineligible; rank eligible routes by the four criteria only — §5.7 |
| D6 | Coverage rule | a route is eligible only with **100 % weather coverage** (every route mile has a known risk). Stated in UI and README |
| D7 | Forecast-interval policy | covering interval + 15-min conservative adjacent check; wind interpolated — §5.4 |
| D8 | Cargo weight | pounds, used **only** for the risk rules. Never sent to TomTom. No axles, dimensions or hazmat invented. `vehicleCommercial` is *not* sent unless live spike T2 shows truck mode alone allows commercial-barred roads; if sent, it is disclosed as the one routing assumption |
| D9 | ETA | cumulative from TomTom guidance offsets; fallback uniform speed, flagged `estimated` |
| D10 | Time zones | departure = **origin local** time (IANA zone from coordinates); UTC internally; checkpoint ETAs shown in each checkpoint's zone |
| D11 | Alternatives | provider-returned only; dedupe; honest count message — §5.1 |
| D12 | Heatmap | hybrid overview + exact markers/segments; grid in real miles — §6 |
| D13 | Departure window | now −15 min … +7 days (keeps trip + 48 h inside Open-Meteo's 15-day end limit) |
| D14 | Hosting | Render free, single Docker container; **no keep-alive dependency**; cold start documented and tested; alt: Hugging Face Spaces |
| D15 | Frontend state | plain React hooks (`useState`/`useReducer`/context) + `fetch` with `AbortController`. No Zustand / TanStack Query |
| D16 | Licence | free Open-Meteo tier is non-commercial; attribution shown |

---

## 4. Stack and version policy

| Layer | Choice |
|---|---|
| Backend | Python 3.12 · **Django 5.2 LTS** · Django REST Framework 3.18 · drf-spectacular · httpx · tzdata + offline time-zone lookup (`tzfpy`, fallback `timezonefinder`) · gunicorn · WhiteNoise |
| Frontend | React + TypeScript + Vite · Tailwind CSS · **MapLibre GL JS** (plain, thin wrapper) · Vitest + Testing Library · ESLint/Prettier |
| Routing / geocoding | TomTom Routing + Search |
| Weather | Open-Meteo |
| Basemap | OpenFreeMap "Positron" (no key; we add attribution because the style carries none) |
| Quality | pytest · respx · ruff · mypy (domain, services) · GitHub Actions |

**Version policy (PDF §6):** versions are chosen at scaffold time after checking peer ranges, then **pinned**; the newest major is used only where compatibility is demonstrated (`pip check`, `npm ls`, full test run, build). Where it is not, use the previous mature major. Django 5.2 LTS is chosen over 6.x for third-party compatibility.

---

## 5. Backend specifications

### 5.1 Route retrieval and the alternatives policy

TomTom `GET /routing/1/calculateRoute/{olat},{olon}:{dlat},{dlon}/json`:
`travelMode=truck` · `routeType=fastest` · `traffic=true` · `departAt=<UTC RFC 3339>` · `maxAlternatives=2` · `routeRepresentation=encodedPolyline` · `instructionsType=coded`.
**Not sent:** `vehicleWeight`, axle count, dimensions, hazmat (D8).

1. Ask for the provider's native alternatives only. Never issue extra waypoint/circle requests to "reach three".
2. Normalise each returned route to `RawRoute{points, distance_m, duration_s, time_offsets[(m, s)], via_label}`; discard routes with missing geometry, duration or length.
3. **Deduplicate** by geometry + distance + duration: route B is a duplicate of kept route A when ≥ 95 % of B's 2-mile samples lie within 0.5 mi of A **and** vice-versa, **and** distance and duration are each within 3 %. The faster is kept. Thresholds are checked against live spike data (T1 prints pairwise share ratios) before they are frozen.
4. Sort by duration; name **Route A/B/C** (stable); label `via` from road numbers when present.
5. Report honestly: `alternatives = {requested: 3, returned: n_raw, usable: n_kept, message}` — e.g. *"The routing provider returned 2 valid alternatives for this trip."* One route → *"The routing provider returned no alternative routes for this trip."* UI shows exactly how many routes exist. Nothing is fabricated or implied to come from the provider.
6. No slowness filter: a slower provider alternative can legitimately be the safer one; the trade-off (+minutes) is explained in the recommendation.

### 5.2 Checkpoints and segment ownership

- Decode polyline → **decimate** (keep a point only if ≥ 50 m from the last kept) → cumulative haversine miles → **scaled** so the total equals TomTom's `lengthInMeters`.
- Checkpoints at d = 0, N, 2N, … **while d ≤ D − 0.25 N**, plus **always the destination** at D (so a near-duplicate checkpoint just before the end is dropped). Examples: D=100,N=25 → 0,25,50,75,100 · D=101 → 0,25,50,75,101 · D=10,N=25 → 0,10.
- Position by linear interpolation along the polyline.
- **Midpoint ownership:** checkpoint *i* owns the stretch from the midpoint with its predecessor to the midpoint with its successor (first owns from 0, last owns to D). Miles per risk level therefore **sum exactly to D**.
- Cap: > 300 checkpoints per route at the chosen interval → interval is raised to the next option and the response says so.

### 5.3 Weather retrieval, unit normalisation, missing data

- Request: `latitude=…&longitude=…&hourly=wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,temperature_2m&wind_speed_unit=mph&precipitation_unit=inch&temperature_unit=fahrenheit&timezone=GMT&start_hour=…&end_hour=…`.
- Coordinates are rounded to **0.01°** (≈ 1 km, finer than the forecast models' grids); the rounded value is both the query and the cache key. Results are matched to requests **by order**.
- ≤ 100 locations per request, ≤ 6 requests in parallel, 3 attempts on 429/5xx with back-off (honour `Retry-After`), timeouts 3 s connect / 15 s read. `end_hour` is clamped to today+15 days.
- **Normalisation (`weather/normalize.py`)** reads `hourly_units` from every response and converts using a closed table — any unrecognised unit string raises, nothing is guessed:

| Quantity | Accepted source units → normalised |
|---|---|
| wind | `mp/h` (×1), `km/h` (×0.621371), `m/s` (×2.236936), `kn` (×1.150779) → **mph** |
| rain (rain + showers) | `inch` (×1), `mm` (÷25.4) → **in/hr** (accumulation over one hour) |
| snowfall | `inch` (×1), `cm` (÷2.54) → **in/hr**. Inspected per response; never inferred from the precipitation setting |
| temperature | `°F`, `°C` → °F |

- **Rain = `rain` + `showers`.** Open-Meteo reports large-scale rain and convective showers separately; both fall as liquid on the road and the brief's rain thresholds concern liquid rainfall rate. `precipitation` is not used because it also contains snow water-equivalent. If either component is missing the rain value is missing.
- Normalised values are stored with their units, the **source stamp** and the source units. Converted values are rounded to 6 decimals to remove float noise before comparison.
- **Missing data stays missing.** `None` never becomes 0, never becomes Low. Failed chunks → their checkpoints are **Unknown**; `meta.warnings` lists them; if *every* chunk fails → HTTP 502 `weather_unavailable`.

### 5.4 ETA and forecast-interval matching policy

**ETA.** `t(d)` is piecewise-linear through TomTom's `(routeOffsetInMeters, travelTimeInSeconds)` guidance points, with (0, 0) and (total length, total time) added; offsets must be monotonic and reach the route end, otherwise the **fallback** applies: uniform speed `t(d) = total_s · d / D`, `eta_method = "estimated_uniform_speed"`, and the UI says "ETAs estimated from average speed". Otherwise `eta_method = "route_guidance"`. `ETA = departure_utc + t(d)`. Durations already include typical traffic for the requested departure time.

**Forecast-interval matching** for an ETA *t* (UTC), with `H = floor_to_hour(t)` and `f = t − H`:

| Field | Meaning in the data | Rule |
|---|---|---|
| rain, showers, snowfall (stamp *S*) | sum over the **preceding** hour `[S−1h, S)` | use the interval that **covers** *t*, i.e. `[H, H+1h)` → record stamped **H+1h**. Half-open: *t* exactly on the hour belongs to the interval starting at *t* |
| wind (stamp *S*) | instantaneous value at *S* | **linear interpolation** between stamps **H** and **H+1h** at weight `f/1h` |
| conservative adjacency | ETA is itself an estimate | if `f < 15 min` also evaluate the previous interval (stamp **H**); if `f ≥ 45 min` also evaluate the next interval (stamp **H+2h**); keep the **worse** risk |

Missing handling: if a stamp needed by the **covering** candidate is absent or null → that checkpoint is **Unknown** (§5.6). Missing adjacent stamps are ignored (they only add caution). The checkpoint reports `basis = {precip_intervals, wind_stamps, adjacent_interval_used}` so the popup can show exactly which forecast hours were used.

| ETA (UTC) | precipitation record(s) | wind |
|---|---|---|
| 14:00:00 | 15:00 (covers 14:00–15:00) **+ 14:00** (adjacent, f<15 min) | stamp 14:00 |
| 14:20 | 15:00 | 14:00→15:00 at ⅓ |
| 14:50 | 15:00 **+ 16:00** (adjacent, f≥45 min) | 14:00→15:00 at ⅚ |

**The heatmap uses the same function** with *t* = departure + h hours (h = 0…48), so overview and checkpoints can never disagree on policy. Fetch window: `[floor_hour(dep), floor_hour(dep)+50 h]` = 51 stamps (matches the spike).

### 5.5 Time zones and daylight-saving time

- Form sends `departure_local` (naive `YYYY-MM-DDTHH:MM`) — **no browser zone involved**. The backend finds the origin's IANA zone from its coordinates (offline lookup) and converts with `zoneinfo`.
- **Nonexistent local time** (spring-forward gap, e.g. 2026-03-08 02:30 America/Chicago) → HTTP 400 `invalid_departure_time` naming the gap and the next valid time.
- **Ambiguous local time** (fall-back, e.g. 2026-11-01 01:30 America/Chicago) → the **first** occurrence (daylight time) is used and the response carries a warning with both UTC instants.
- Validity window: `departure_utc ∈ [now − 15 min, now + 7 days]`.
- UI shows the origin zone beside the departure field ("America/Chicago · CDT"). Each checkpoint carries its own IANA zone (offline lookup; if a lookup fails the previous checkpoint's zone is reused) and the UI formats its ETA in that zone with the abbreviation. The heatmap slider label uses the origin zone. Abbreviations come from `zoneinfo`, never from Open-Meteo.

### 5.6 Risk engine specification

Levels: **Low 0 · Moderate 1 · High 2 · Severe 3 · No Travel 4**. *Unknown* is not a level — it is `level = None`.

| Level | Wind (mph) | Rain (in/hr) | Snow (in/hr) |
|---|---|---|---|
| Low | x < 25 | x < 0.10 | x < 0.5 |
| Moderate | 25 ≤ x < 35 | 0.10 ≤ x < 0.25 | 0.5 ≤ x < 1.0 |
| High | 35 ≤ x < 45 | 0.25 ≤ x < 0.50 | 1.0 ≤ x < 2.0 |
| Severe | 45 ≤ x < 55 | 0.50 ≤ x ≤ 1.00 | 2.0 ≤ x ≤ 3.0 |
| No Travel | x ≥ 55 | x > 1.00 | x > 3.0 |

**Convention (PDF §3):** Low is below the first threshold; every later band includes its lower bound and excludes its upper bound; No Travel begins **strictly above** the printed Severe upper bound for rain and snow (so exactly 1.00 in/hr and 3.0 in/hr are *Severe*); wind No Travel is printed "≥ 55". Every exact boundary and the values just below/above it are tested (`math.nextafter`).

**Load rules** (cargo pounds, strict "greater than"), applied as a **floor**:
wind ≥ 55 → No Travel (any load) · 45 ≤ wind < 55 and load > 30 000 → **No Travel** · 35 ≤ wind < 45 and load > 40 000 → **Severe**.
`level = max(wind, rain, snow, load floor)`.

**Missing inputs:** if any of wind/rain/snow is missing: compute the floor from the known ones; if that floor is **No Travel** the checkpoint is No Travel (it cannot get better), otherwise the checkpoint is **Unknown** with `at_least = floor` and `missing = [...]`. Negative, NaN or infinite readings count as missing.

`drivers[]` lists every factor at Moderate or above and the load rule when it raised the level (shown as "why"). Thresholds are data tables, not scattered `if`s.

### 5.7 Coverage, eligibility, ranking and explanation

Per route (`domain/scoring.py`), using midpoint ownership:
- `miles_by_level` {low, moderate, high, severe, no_travel, unknown}; `no_travel_mi`, `severe_mi`, `high_mi`.
- `coverage = 1 − unknown_mi / total_mi` (shown as a percentage).
- `avg_risk` = Σ(score × owned miles over **known** checkpoints) / known miles, scores Low 0 · Moderate 1 · High 2 · Severe 3 · No Travel 4 (the 4 only ever appears on ineligible routes); `None` if nothing is known.

**Eligibility** (hard gates, never ranking factors):
1. `no_travel_mi > 0` → ineligible, reason `no_travel`.
2. `coverage < 1.0` → ineligible, reason `incomplete_weather` (so a route cannot look safer merely because unknown sections are excluded from its average).

**Ranking** — eligible routes only, ascending by
`(round(severe_mi, 1), round(high_mi, 1), round(avg_risk, 2), duration_s)`; rounding only removes float noise; exact ties fall back to provider order.

**Status**
| Situation | `recommendation.status` | UI |
|---|---|---|
| ≥ 1 eligible route | `recommended` (first of ranking) | ★ Recommended + reasons |
| every returned route has No Travel miles | `no_safe_route` | **"No safe route available"** — routes and hazards still shown; **no route labelled Recommended** |
| none eligible and not all blocked (incomplete weather) | `inconclusive` | "A safe recommendation cannot be determined" + per-route coverage |

**Explanation:** compare the winner with every other route on the first differing criterion ("Fewest Severe miles: 0 vs 33 on Route A") and state its duration, coverage and the hazards it still contains ("includes 25 mi of High risk"). Never say "risk-free". A single returned route that is eligible is recommended as "the only available route".

### 5.8 Errors and edge cases

| Case | Behaviour |
|---|---|
| invalid input (coords, interval ∉ {10,25,50}, weight ∉ (0, 150 000], origin≈destination < 5 mi, departure outside window) | 400 `validation_error` with per-field messages |
| nonexistent local departure time | 400 `invalid_departure_time` (§5.5) |
| geocoder returns nothing | empty list → inline "no match" |
| TomTom no route / > 3 500 mi | 422 `no_route` / `trip_too_long` |
| TomTom timeout / 5xx / quota | 502/503 `routing_unavailable` + `retry_after_s` |
| Open-Meteo 429 | back-off retry; still failing → affected checkpoints Unknown; all failing → 502 |
| Open-Meteo 400 "out of range" | window clamped; later hours Unknown |
| 1–2 routes returned | shown with the count message (§5.1) |
| `eta_method = estimated_uniform_speed` | flagged on route + banner |

---

## 6. Heatmap data and rendering plan (hybrid)

**Why hybrid.** A kernel-density heat layer blends neighbouring values (a Low next to a Severe renders as an "in-between" colour that is no real category). It is useful for corridor overview, so it stays — but **exact categories come from discrete layers** that are authoritative.

**Data (`domain/heatmap.py`, `POST /api/heatmap`)**
- **Grid in real distance.** Rows are spaced `CELL_MILES = 15` apart north–south (Δlat = 15/69 °). Within each row the longitude step is `15 / (69.17·cos φ)` degrees, so **east–west spacing is also 15 mi at every latitude** (a fixed 0.25° grid would be ≈ 13 mi at 40° N and ≈ 9 mi at 60° N — not used). Cell centres are deterministic (row/column indices) so neighbouring trips share cache entries.
- **Corridor** = union of cells whose centre lies within `HALF_WIDTH_MILES = 20` of any returned route (routes sampled every 5 mi); shared stretches are not double counted. The number of cells is **measured**, never assumed (`meta.cells`; reported in README after benchmarking Chicago→Denver, Dallas→Atlanta, Seattle→Salt Lake City).
- Hourly levels use the **same** `select_forecast` + `assess_risk` + the user's cargo weight. Payload per cell: `levels` = 49 characters (hour 0…48): `0–4` known, `9` unknown.
- Stateless: the client posts the encoded polylines + `departure_utc` + cargo weight it already has; the server caps polyline size, route count and length.

**Rendering (frontend)**
1. **Overview** — MapLibre `heatmap` layer (inserted below the basemap's labels), weights Low 0.1 · Moderate 0.3 · High 0.5 · Severe 0.75 · No Travel 1.0; Unknown cells have weight 0 **and** are drawn as small hollow grey dots so missing data never looks like "Low". Labelled *"Smoothed forecast overview at slider time"*.
2. **Exact checkpoint markers** (all routes) — circles coloured by level with text/shape cues; Unknown = hollow grey; **authoritative**.
3. **Risk-coloured route segments** for the selected route (each owned stretch coloured by its checkpoint's level; Unknown dashed grey); unselected routes keep their identity colours.
4. **Legend** with Low, Moderate, High, Severe, No Travel, Unknown, plus the sentence *"Markers and route colours show exact categories at your ETA; the heat layer is smoothed."*
5. **Slider** 0–48 h (origin-zone label, ▶ play): **all 49 hours are preloaded** in one `Uint8Array`; scrubbing only changes weights locally — **zero network requests per movement**. Clicking a checkpoint moves the slider to that checkpoint's ETA hour when it is within 0–48 h.

---

## 7. API contract (OpenAPI served at `/api/docs/`)

**`POST /api/plan`** request
```json
{ "origin": {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298},
  "destination": {"label": "Denver, CO", "lat": 39.7392, "lon": -104.9903},
  "departure_local": "2026-11-02T06:00", "cargo_weight_lb": 42000, "interval_miles": 25 }
```
response (abbreviated)
```jsonc
{ "request": { "origin_timezone": "America/Chicago", "departure_local": "2026-11-02T06:00:00-06:00",
               "departure_utc": "2026-11-02T12:00:00Z", "interval_miles": 25, "interval_adjusted": false,
               "cargo_weight_lb": 42000, "warnings": [] },
  "alternatives": { "requested": 3, "returned": 2, "usable": 2,
                    "message": "The routing provider returned 2 valid alternatives for this trip." },
  "routes": [{
    "id": "A", "name": "Route A", "via": "I-80 W", "distance_mi": 1003.2, "duration_s": 60120,
    "arrival_utc": "2026-11-03T04:42:00Z", "arrival_tz": "America/Denver",
    "eta_method": "route_guidance",                      // or "estimated_uniform_speed"
    "geometry": {"type": "LineString", "coordinates": [[-87.63, 41.88], "…"]},
    "polyline": "<precision-5 encoded display geometry; send this back to /api/heatmap>",
    "segments": [{"from_mi": 0, "to_mi": 12.5, "level": "low", "coordinates": [[-87.63, 41.88], "…"]}],
    "summary": { "miles_by_level": {"low": 880.2, "moderate": 60.0, "high": 30.0, "severe": 33.0, "no_travel": 0.0, "unknown": 0.0},
                 "coverage_pct": 100.0, "no_travel_mi": 0.0, "severe_mi": 33.0, "high_mi": 30.0,
                 "avg_risk": 0.41, "max_level": "severe", "checkpoint_count": 41 },
    "eligibility": { "eligible": true, "reasons": [] },  // reasons ⊂ ["no_travel", "incomplete_weather"]
    "checkpoints": [{
      "i": 12, "mile": 300.0, "lat": 41.2, "lon": -96.1, "eta_utc": "2026-11-02T22:10:00Z", "tz": "America/Chicago",
      "weather": { "wind_mph": 41.2, "gust_mph": 52.0, "rain_in_hr": 0.0, "snow_in_hr": 0.0, "temp_f": 38.0,
                   "basis": { "precip_intervals": [["2026-11-02T22:00:00Z", "2026-11-02T23:00:00Z"]],
                              "wind_stamps": ["2026-11-02T22:00:00Z", "2026-11-02T23:00:00Z"], "adjacent_interval_used": false },
                   "source_units": {"wind": "mp/h", "rain": "inch", "snow": "inch"} },
      "risk": { "level": "severe", "score": 3, "at_least": null, "missing": [],
                "drivers": [{"factor": "load_rule", "level": "severe", "text": "42,000 lb cargo with 35–44 mph wind"}] } }] }],
  "recommendation": { "status": "recommended", "route_id": "B", "ranking": ["B", "C", "A"],
                      "headline": "Route B is the safest eligible route",
                      "reasons": ["Fewest Severe miles: 0 vs 33 on Route A"], "caveats": ["Still includes 30 mi of High risk"] },
  "meta": { "routing_provider": "tomtom", "weather_provider": "open-meteo", "weather_model": "best_match",
            "timings_ms": {"routing": 1800, "weather": 900, "total": 3100}, "weather_cache": {"hits": 40, "misses": 83} } }
```
`recommendation.status` ∈ `recommended | no_safe_route | inconclusive`; `route_id` is `null` unless `recommended`. `risk.level` ∈ `low | moderate | high | severe | no_travel | unknown`.

**`POST /api/heatmap`** — request `{ routes: [{id, polyline}], departure_utc, cargo_weight_lb }` → `{ start_utc, hours: 49, cell_miles: 15, half_width_miles: 20, cells: [{lat, lon, levels: "0012…"}], meta: {cells, unknown_cells, timings_ms} }`.
**`GET /api/geocode?q=`** → `{ results: [{label, lat, lon, timezone}] }` (IANA zone computed offline).
**`GET /api/health/`** → `{status: "ok"}` · `GET /api/schema/`, `/api/docs/`.
Errors: `{ "error": {"code", "message", "retry_after_s?"} }` — `validation_error`(400) · `invalid_departure_time`(400) · `no_route`/`trip_too_long`(422) · `rate_limited`(429) · `routing_unavailable`/`weather_unavailable`(502) · `quota_exceeded`(503). Throttles per IP: plan + heatmap 20/min, geocode 60/min.

---

## 8. Frontend plan

- **State:** plain React hooks + a small context; typed `fetch` client with `AbortController`; auto-retry (2 s, 5 s, 10 s) on network errors / 502 / 503 / 504 with a visible "server is starting up or busy — retrying" message and a manual Retry (graceful cold start, no keep-alive assumption).
- **Form:** origin/destination comboboxes (debounce 300 ms, ≥ 3 chars, abort stale, keyboard nav) · departure `datetime-local` with the **origin time zone shown beside it** · **Cargo/load weight (lb)** with the rule thresholds as helper text · interval control 10/25/50.
- **Results:** `RecommendationBanner` for all three statuses (Recommended / **No safe route available** / **Cannot be determined**) · alternatives message · `RouteCard` (summary, ETA method label, **coverage %**, Severe/High miles, avg risk, eligibility badge + reasons, risk strip) · `CheckpointTable` (selected route; ETA in checkpoint zone; values with units; forecast hours used) · `RulesDrawer` (the exact rule tables) · attribution footer.
- **Map:** plain `maplibre-gl` + thin lifecycle wrapper (`map/` modules). Layers per §6; route chips ("B ★ · 17 h 30 · 1 012 mi"); popups with ETA + values + reasons; route selection from map/cards/table.
- **States:** validation · loading (steps: routes → forecast → scoring) · no routes · one/two routes · all blocked · incomplete weather · estimated ETAs · API error · heatmap loading/failed (routes still usable) · mobile bottom-sheet layout.
- **Accessibility:** labelled inputs, `aria-live` results, keyboard slider/combobox, visible focus, AA contrast, risk never colour-only (text + icon + marker shape), `prefers-reduced-motion` disables auto-play.
- **Parallel track:** the frontend is independent of the backend internals (it follows §7) and can be built against fixtures. **Use `docs/api-examples/*.json` as the fixtures** — they are real output of the backend pipeline (synthetic routing + demo weather): `plan_storm` (Route B has No Travel miles → ineligible, Route C recommended), `plan_calm`, `plan_two_routes`, `plan_no_safe_route`, `plan_inconclusive` (Unknown checkpoints, coverage ~53 %), `plan_estimated_eta`, `heatmap_storm` (469 cells), request bodies and the error envelopes. Each route also carries `polyline` (precision-5 encoding of the display geometry) — post it back unchanged to `/api/heatmap`; no client-side encoder is needed.

---

## 9. Architecture and repository layout

```
Browser (React + MapLibre) ──POST /api/plan · POST /api/heatmap · GET /api/geocode──▶ Django + DRF
   api/        thin views, serializers, throttles, error mapping
   planner.py  routes → checkpoints → forecast → risk → coverage/eligibility → ranking
   domain/     PURE Python, no I/O: types · geo · polyline · timezones · eta · forecast · risk · checkpoints · scoring · heatmap · route_filters
   services/   adapters behind Protocols: routing (tomtom) · geocoding (tomtom) · weather (open_meteo, normalize, cache, mock)
```
```
Truck Routing/
├─ backend/   manage.py · requirements*.txt · pyproject.toml · config/ · trucking/{api,domain,services,tests}
├─ frontend/  src/{api,components,map,state,utils}
├─ docs/      PLAN.md · spike/ · ACCEPTANCE.md · WALKTHROUGH.md · screenshots/
├─ scripts/   spike/ · smoke_live.py
├─ Dockerfile · render.yaml · .env.example · .gitignore · .github/workflows/ci.yml · README.md
```
Domain code never imports Django or does I/O; tests inject fakes. No database, models or migrations (stateless).

Caches (in-process, size-bounded, TTL): weather by (rounded coords, window) 30 min · routing by (origin, destination, departure hour) 15 min · geocode 1 h. Single gunicorn worker × threads so the cache is shared.

---

## 10. Test matrix (PDF §7) → modules

| Group | Required cases | Tests |
|---|---|---|
| Risk thresholds | every exact wind/rain/snow boundary; just below / above (`nextafter`); unit conversions | `test_risk.py`, `test_normalize.py` |
| Load overrides | all 3 rules; 30 000 vs 30 001 lb; 40 000 vs 40 001 lb; wind ≥ 55 any load; floor never lowers | `test_risk.py` |
| Recommendation | lexicographic order per criterion; No Travel ineligible; all blocked → none; tie → duration; single eligible; inconclusive | `test_scoring.py` |
| Weather coverage | Unknown never Low; partially known + No Travel; low-coverage route cannot win; coverage % correct | `test_risk.py`, `test_scoring.py`, `test_planner.py` |
| Checkpoint spacing | 10/25/50; destination rule; short routes; interpolation; ownership sums to total | `test_checkpoints.py`, `test_geo.py` |
| ETA and time zones | cumulative ETA (guidance) + flagged fallback; between-hour lookup + adjacency; origin zone; route crossing zones; DST ambiguous (2026-11-01 01:30 Chicago) and nonexistent (2026-03-08 02:30 Chicago) | `test_eta.py`, `test_forecast_select.py`, `test_timezones.py` |
| Provider failures | timeout, 429, invalid response, missing variable, partial forecast, no alternatives, 1–2 routes | `test_open_meteo_client.py`, `test_tomtom_adapter.py`, `test_planner.py`, `test_api.py` |
| Heatmap | hour 0 and 48; payload shape; unknown handling; spacing is 15 mi at 30°/45°/60° N; scrubbing uses preloaded data (no fetch) | `test_heatmap.py`, frontend tests |
| Frontend states | validation, loading, no routes, one/two routes, all blocked, incomplete weather, API error, mobile | component tests + manual checklist |
| End to end | trip from input → routes → checkpoint weather → risk → recommendation → map | `test_api_e2e.py` (fake providers), `scripts/smoke_live.py` (real), browser pass |

---

## 11. Performance targets (to be measured, then recorded in `docs/PERFORMANCE.md`)

| Target | Measured how |
|---|---|
| plan response < 6 s cold / < 1.5 s warm | `meta.timings_ms` over 4 trips × 3 intervals |
| heatmap cells and payload for realistic routes | counted per trip; reported in README. *First measurement (3 synthetic Chicago→Denver routes, 15 mi cells, 20 mi half-width): 469 cells, 54 KB JSON — real routes to be re-measured* |
| slider scrub / play ≥ 55 fps | `requestAnimationFrame` frame-time probe while scripting the slider (after end-to-end works) |
| initial JS < 150 KB gz before the lazy map chunk | build report |
| Lighthouse performance ≥ 90 (desktop) | Lighthouse run |

---

## 12. Deployment and cold start

- **One Docker container** (multi-stage: Node builds the SPA; Python 3.12-slim serves API + static via WhiteNoise, `gunicorn --workers 1 --threads 8`). `/api/health/`; secrets only in environment variables (`DJANGO_SECRET_KEY`, `TOMTOM_API_KEY`, `DJANGO_ALLOWED_HOSTS`, …); `.env` is git-ignored; `.env.example` committed.
- **Cold start:** Render free sleeps after 15 min idle and wakes in ≈ 1 min. **No keep-alive is required or relied on.** The SPA is served by the same container, so the page loads once the service is awake; the client retries transient failures with a visible message. README documents the behaviour; M7 includes a timed idle-then-request test; the filesystem is treated as ephemeral (nothing persistent; caches are in memory).
- **Open-Meteo on shared hosting:** limits are per IP; caching + 429 handling are mandatory; behaviour documented; commercial use would need a paid plan.
- Fallback host if Render's free tier proves unusable: Hugging Face Spaces (Docker).

---

## 13. Documentation and Loom

README: overview + live link + screenshots · setup (Windows PowerShell, macOS/Linux) · env vars · APIs used + **attribution** (Open-Meteo CC BY 4.0, TomTom, OpenStreetMap/OpenFreeMap) · risk rules + boundary convention + load rules · eligibility/coverage/ranking · ETA and forecast-interval policy · time-zone/DST behaviour · alternatives policy · assumptions and limitations (no ice/fog/visibility, continuous-driving ETAs, non-commercial weather tier) · tests · deployment/cold start · spike report link.
Loom script (`docs/WALKTHROUGH.md`, ≈ 8 min): problem → live trip → recommendation reasons → checkpoint popup with a load-rule example → heatmap + exact markers → a No-Travel / all-blocked case (mock weather scenario) → code tour of `risk.py`/`scoring.py`/tests → performance numbers → limitations.

---

## 14. Build plan

| M | Work | Gate / done when |
|---|---|---|
| **M0** | Repo scaffold, git init, backend/frontend skeletons, CI, spike evidence committed | health endpoint + test runner green; Open-Meteo evidence ✅ |
| **M1** | Domain core + exhaustive tests (types, geo, polyline, timezones, eta, forecast, risk, checkpoints, scoring, heatmap, route_filters) | all §10 domain cases pass |
| **M2** | Open-Meteo client + normaliser + cache; routing/geocoding Protocols + fakes; **TomTom live spike → adapter** | adapter only after live spike reviewed (HOLD) |
| **M3** | Planner + DRF API + OpenAPI + throttles + error mapping | API tests green incl. failure cases |
| **M4** | Frontend core (form, results, map, popups) — *parallel track* | works on contract fixtures, then real API |
| **M5** | Heatmap hybrid + slider + legend; benchmark cells/fps | PDF §4.8 items verified |
| **M6** | States, mobile, a11y, palette check, polish | acceptance rows 1–15 pass |
| **M7** | Docker, Render, deployed health check, cold-start test | deployed check ✅, behaviour documented |
| **M8** | README, `docs/ACCEPTANCE.md`, Loom script; `simplify` + `code-review` passes | all §16 items ticked with evidence |

---

## 15. Traceability — every original requirement → module · API · UI · test

| # | Requirement | Module(s) | API | UI | Tests |
|---|---|---|---|---|---|
| R1 | Origin & destination | `geocoding/tomtom.py`, `timezones.py` | `GET /api/geocode`, `plan.request` | `PlaceInput` ×2 | geocode API test, `PlaceInput` test |
| R2 | Departure date/time | `timezones.py`, `api/serializers.py` | `departure_local` → `departure_utc`, `origin_timezone` | departure field + zone label | `test_timezones.py`, form test |
| R3 | Load weight | `risk.py`, `serializers.py` | `cargo_weight_lb` | "Cargo/load weight (lb)" | `test_risk.py`, form test |
| R4 | 3 route options from a routing API | `routing/tomtom.py`, `route_filters.py` | `routes[]`, `alternatives` | route cards, count message | `test_tomtom_adapter.py`, `test_route_filters.py` |
| R5 | Weather every 10/25/50 mi at ETA | `checkpoints.py`, `eta.py`, `forecast.py`, `open_meteo.py` | `checkpoints[]`, `interval_miles` | interval control, popups, table | `test_checkpoints.py`, `test_eta.py`, `test_forecast_select.py`, `test_open_meteo_client.py` |
| R6 | Risk from provided rules + load rules | `risk.py`, `normalize.py` | `risk`, `weather.*` | badges, drivers text, Rules drawer | `test_risk.py`, `test_normalize.py` |
| R7 | Recommend best route (risk vs time, preference order) | `scoring.py` | `recommendation`, `eligibility` | banner, ★, reasons | `test_scoring.py` |
| R8 | Routes, checkpoints, risk, ETAs, summaries on map | `planner.py`, serializers | `routes[].{geometry,segments,summary,checkpoints}` | map layers, chips, popups, risk-coloured segments | component tests, e2e, manual checklist |
| R9 | Heatmap + 0–48 h slider | `heatmap.py`, `forecast.py` | `POST /api/heatmap` | heat layer, markers, legend, `TimeSlider` | `test_heatmap.py`, slider test (no fetch) |
| R10 | GitHub repo | repo + CI | — | — | CI green |
| R11 | Hosted app | Dockerfile, `render.yaml` | `/api/health/` | — | deployed smoke |
| R12 | Loom 5–10 min | `docs/WALKTHROUGH.md` | — | — | rehearsal |
| C1 | No Travel ineligible; no false recommendation | `scoring.py` | `recommendation.status` | banners | `test_scoring.py` |
| C2 | Cargo weight not sent as vehicleWeight | `tomtom.py` | — | — | adapter test asserts params |
| C3 | Units + accumulation intervals | `normalize.py`, `forecast.py` | `weather.basis` | popup basis text | `test_normalize.py`, `test_forecast_select.py` |
| C4 | Origin time zone, DST | `timezones.py` | `origin_timezone`, `tz` | zone labels | `test_timezones.py` |
| C5 | Honest alternatives | `route_filters.py` | `alternatives` | message | planner/adapter tests |
| C6 | Unknown + coverage | `risk.py`, `scoring.py` | `coverage_pct`, `unknown` | grey markers, coverage % | `test_scoring.py` |
| C7 | Hybrid heatmap, real-mile grid | `heatmap.py` | `cell_miles` | layers + legend | `test_heatmap.py` |

---

## 16. Final acceptance checklist (evidence recorded in `docs/ACCEPTANCE.md`)

1. Inputs: origin, destination, departure date/time, cargo weight.
2. Departure interpreted in the origin's local time zone (zone shown beside the field).
3. Genuine truck routes requested; the number actually returned is displayed.
4. 10 / 25 / 50-mile sampling choices work.
5. Checkpoint ETAs come from route travel-time data and are labelled (estimated when fallback).
6. Units normalised to mph and in/hr before risk calculation.
7. Hourly precipitation matched to the correct forecast interval.
8. All thresholds and load rules implemented and boundary-tested.
9. Unknown stays Unknown; coverage visible.
10. A route with No Travel miles is not eligible for recommendation.
11. Eligible routes ranked by Severe mi → High mi → avg risk → duration.
12. All-blocked or insufficient coverage → no false recommendation.
13. Map shows all returned routes, checkpoints, risk levels, ETAs, summaries.
14. Heatmap corridor + 0–48 h slider work; exact markers remain distinguishable.
15. Slider makes no weather request per movement.
16. Errors, missing data, limited alternatives, provider failures explained to the user.
17. Automated tests cover risk engine, ranking, units, ETA/time zones, failure cases.
18. Deployed app usable after a cold start; secrets not committed.
19. README covers setup, APIs, assumptions, risk rules, limitations, attribution, deployment.
20. GitHub repository, hosted app and 5–10 min Loom delivered.

---

## 17. Open items and deferred work

- **Needed from the user:** a free **TomTom API key** (developer.tomtom.com → create key; no card) placed in `backend/.env` as `TOMTOM_API_KEY=…` (never committed) — unblocks the TomTom live spike; later an empty GitHub repo and a Render account.
- **Deferred (PDF §6):** OSRM/Photon fallback, waypoint route generation, elaborate state management, instrumentation before end-to-end works, wind/rain/snow layer switch, truck-position dot, departure-time advisor, HOS planning, vehicle-spec form, accounts, dark mode.
