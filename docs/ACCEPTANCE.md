# Final acceptance checklist

Status legend: ✅ done and verified · 🟡 built, awaiting live/external verification · ⬜ not started.
The project is **not complete** until every row is ✅ (review document, section 8).

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | User can enter origin, destination, departure date/time and cargo weight | 🟡 | `PlanRequestSerializer` + API tests (`test_api.py`); form is the frontend track |
| 2 | Departure interpreted in the origin's local time zone | ✅ backend | `test_timezones.py`, `test_planner.py::test_departure_is_interpreted_in_the_origin_zone…`; UI zone label pending frontend |
| 3 | Genuine truck routes requested; number actually returned is displayed | 🟡 | `alternatives` block + `test_planner.py` (1/2/3 routes, duplicates); TomTom live run pending |
| 4 | 10 / 25 / 50-mile sampling | ✅ backend | `test_checkpoints`, `test_planner.py::test_checkpoint_count_follows_the_interval` |
| 5 | Checkpoint ETAs from route travel-time data, labelled | 🟡 | `eta.py` + tests; fallback flagged `estimated_uniform_speed`; TomTom guidance offsets to be confirmed live |
| 6 | Units normalised to mph and in/hr before risk | ✅ | `test_normalize.py` (incl. real `mp/h` response), `SPIKE_REPORT.md` |
| 7 | Hourly precipitation matched to the correct forecast interval | ✅ | `forecast.py`, `test_forecast_select.py` |
| 8 | All thresholds and load rules implemented and boundary-tested | ✅ | `test_risk.py` (every boundary ±`nextafter`, 30,000/30,001 and 40,000/40,001 lb) |
| 9 | Unknown stays Unknown; coverage visible | ✅ backend | `test_risk.py`, `test_scoring.py`, `test_planner.py::test_partial_forecast…`; UI pending |
| 10 | Route with No Travel miles not eligible | ✅ | `test_scoring.py`, `test_planner.py::test_blocked_route_is_excluded…` |
| 11 | Eligible routes ranked Severe → High → avg risk → duration | ✅ | `test_scoring.py` |
| 12 | All blocked / insufficient coverage → no false recommendation | ✅ | `test_scoring.py`, `test_planner.py::test_all_routes_blocked…` |
| 13 | Map shows all routes, checkpoints, risk levels, ETAs, summaries | ⬜ | frontend |
| 14 | Heatmap corridor + 0–48 h slider; exact markers distinguishable | 🟡 | data: `test_heatmap_filters.py`, `test_planner.py`; rendering is the frontend |
| 15 | Slider makes no weather request per movement | ⬜ | frontend test (data is preloaded: 49 hours per cell in one response) |
| 16 | Errors, missing data, limited alternatives, provider failures explained | 🟡 | API error envelope + tests; UI pending |
| 17 | Automated tests cover risk, ranking, units, ETA/time zones, failures | ✅ backend | 254 tests, 98 % domain coverage |
| 18 | Deployed app usable after cold start; secrets not committed | ⬜ | `Dockerfile`, `render.yaml`, `.gitignore` ready; deploy pending |
| 19 | README covers setup, APIs, assumptions, rules, limitations, attribution, deployment | 🟡 | `README.md` (update after live spike + deploy) |
| 20 | GitHub repo, hosted app, 5–10 min Loom delivered | ⬜ | pending |
