# Final acceptance checklist

Status legend: ✅ done and verified · 🟡 built, one external step still open · ⬜ not done.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | User can enter origin, destination, departure date/time and cargo weight | ✅ | `TripForm` + `PlaceInput` (`TripForm.test.tsx`, `PlaceInput.test.tsx`), `PlanRequestSerializer` (`test_api.py`); live typeahead through `/api/geocode` verified against TomTom |
| 2 | Departure interpreted in the origin's local time zone | ✅ | Zone shown beside the field; form sends a naive `departure_local` (`TripForm.test.tsx`); backend `test_timezones.py`, `test_planner.py`; live run: 06:00 Chicago → `departure_utc` 12:00Z |
| 3 | Genuine truck routes requested; number actually returned is displayed | ✅ | `travelMode=truck`, native alternatives only (`test_tomtom_adapter.py`); live run returned 3 routes on 4 trips (`docs/spike/SPIKE_REPORT.md` §2.1); UI shows the provider's count message (`RecommendationBanner.test.tsx`, mock scenarios `two_routes` / `one_route`) |
| 4 | 10 / 25 / 50-mile sampling | ✅ | `test_checkpoints`, `test_planner.py`; live run at 10, 25 and 50 mi (41 / 47 / 54 checkpoints at 25 mi for the three Chicago→Denver routes) |
| 5 | Checkpoint ETAs from route travel-time data, labelled | ✅ | Live TomTom guidance offsets feed `eta.py`: every live route reported `eta_method = route_guidance`; fallback `estimated_uniform_speed` is flagged in the UI (`estimated_eta` scenario, `PlanNotices`) |
| 6 | Units normalised to mph and in/hr before risk | ✅ | `test_normalize.py` (incl. real `mp/h` response), `SPIKE_REPORT.md` |
| 7 | Hourly precipitation matched to the correct forecast interval | ✅ | `forecast.py`, `test_forecast_select.py`; the popup and table list the forecast hours used |
| 8 | All thresholds and load rules implemented and boundary-tested | ✅ | `test_risk.py` (every boundary ±`nextafter`, 30,000/30,001 and 40,000/40,001 lb); Rules drawer shows the same tables (`App.test.tsx`) |
| 9 | Unknown stays Unknown; coverage visible | ✅ | `test_risk.py`, `test_scoring.py`; UI: hollow grey markers, dashed segments, coverage % on every card. Seen live: an Open-Meteo 429 produced Unknown checkpoints and "A safe recommendation cannot be determined" instead of a false Low |
| 10 | Route with No Travel miles not eligible | ✅ | `test_scoring.py`, `RouteCard.test.tsx`, `App.test.tsx` (no ★ on blocked routes) |
| 11 | Eligible routes ranked Severe → High → avg risk → duration | ✅ | `test_scoring.py` |
| 12 | All-blocked or insufficient coverage → no false recommendation | ✅ | `test_scoring.py`, `test_planner.py`, `RecommendationBanner.test.tsx`, scenarios `no_safe_route` and `inconclusive` |
| 13 | Map shows all routes, checkpoints, risk levels, ETAs, summaries | ✅ | `MapController` layers (route lines, risk-coloured segments, checkpoint markers with letters, route chips, pins, popups); verified visually at 1440×900 and 390×844 with live and mock data |
| 14 | Heatmap corridor + 0–48 h slider; exact markers distinguishable | ✅ | Heat layer below labels, Unknown dots, legend sentence; live heatmap 379–584 cells per trip (`docs/PERFORMANCE.md`) |
| 15 | Slider makes no weather request per movement | ✅ | `App.test.tsx` ("loads the heatmap exactly once" then scrubs 5 positions, request count unchanged), `TimeSlider.test.tsx` |
| 16 | Errors, missing data, limited alternatives, provider failures explained | ✅ | `StatusPanels.tsx`, API error envelope tests, scenarios `routing_error`, `cold_start`, `rate_limited`, `validation_error`, `invalid_departure`, `heatmap_failed` |
| 17 | Automated tests cover risk, ranking, units, ETA/time zones, failures | ✅ | Backend 273 tests, 96 % coverage; frontend 80 tests; both run in CI |
| 18 | Deployed app usable after cold start; secrets not committed | 🟡 | Secrets: `.env` is git-ignored, the key never appears in the repository or in logs (httpx request logging is silenced). Cold start: retry behaviour is tested (`retry.test.ts`) and shown by scenario `cold_start`. **Open:** deploy to Render and time a real idle-then-request |
| 19 | README covers setup, APIs, assumptions, rules, limitations, attribution, deployment | ✅ | `README.md`, `frontend/README.md`, `docs/PERFORMANCE.md` |
| 20 | GitHub repo, hosted app, 5–10 min Loom delivered | 🟡 | Repo: pushed. Walkthrough script: `docs/WALKTHROUGH.md`. **Open:** hosted URL and the recording |
