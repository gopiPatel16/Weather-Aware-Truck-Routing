# Loom walkthrough script (target 8 minutes)

Record at 1440×900, browser zoom 100 %. Have the app open on the hosted URL, `docs/PLAN.md` and `backend/trucking/domain/risk.py` in the editor, and a second tab with `?scenario=…` mock links ready (run `npm run dev:mock` locally for the blocked / incomplete-weather cases).

| Time | Show | Say |
|---|---|---|
| 0:00 | App home | "This is a weather-aware truck router: React + Django. A driver enters origin, destination, departure time and load weight, and the app compares real truck routes by the weather the truck will actually meet, at the time it will meet it." |
| 0:30 | Fill the form: Chicago → Denver, tomorrow 06:00, 42,000 lb, 25 mi | "Departure is read in the **origin's** time zone — it's shown beside the field. The helper text under the weight is the assignment's load rules." |
| 1:00 | Press *Find safest route*; point at the loading steps | "TomTom truck routing gives up to three routes, Open-Meteo gives the hourly forecast. The first request after the free host has been idle can take about a minute; the page tells you and retries by itself." |
| 1:30 | Recommendation banner and the route cards | "Every card shows distance, duration, arrival in the *destination's* zone, forecast coverage, Severe and High miles and average risk. The banner says which route is recommended and why — and it never claims a route is risk-free." |
| 2:30 | Click a map checkpoint; open the popup | "ETA at this checkpoint comes from the route's own travel-time data, shown in this checkpoint's zone. Rain and snow are hourly totals, so the popup lists exactly which forecast hours were used; wind is interpolated between two hours." |
| 3:30 | Find a checkpoint whose *Why* line shows the load rule (mock `normal` scenario) | "Wind of 39 mph is only *High* — but with 42,000 lb the load rule (35–44 mph above 40,000 lb) lifts it to *Severe*. Cargo weight is used only here; it is never sent to the routing provider." |
| 4:15 | Heatmap: drag the slider, press ▶, then point at the legend | "All 49 hours load once, so scrubbing makes no request. The heat layer is a smoothed overview; the markers and route colours are the exact categories — a hollow grey ring means *Unknown*, which is never treated as Low." |
| 5:15 | Mock scenarios: `no_safe_route`, then `inconclusive` | "If every route has No Travel miles, nothing is recommended: *No safe route available*. If the forecast is incomplete, the app says a safe recommendation can't be determined and shows each route's coverage." |
| 6:00 | Editor: `risk.py`, `scoring.py`, the boundary tests | "Thresholds live in data tables. Every exact boundary and the value just above and below it is tested, including 1.00 in/hr rain being Severe and 3.0 in/hr snow being Severe. Eligible routes are ranked by Severe miles, High miles, average risk, then time — a route with No Travel miles can't be recommended at all." |
| 7:00 | `docs/PERFORMANCE.md`, CI badge or Actions run | "Measured numbers are in the performance doc. Backend: 273 tests, 96 % coverage; frontend: 80 tests; lint, types and build run in CI." |
| 7:30 | README limitations | "Limits: wind, rain and snow only (no ice or fog); ETAs assume continuous driving; the free weather API is non-commercial and rate-limited, so long routes at a 10-mile interval can come back with Unknown sections — the app reports that honestly. Thanks for watching." |

## Checklist before recording
- [ ] Hosted URL loads and `/api/health/` answers (wake the service first if it was idle).
- [ ] One real trip works end to end; note its recommendation text so you can read it out.
- [ ] Mock tabs open: `?scenario=normal`, `no_safe_route`, `inconclusive`.
- [ ] Notifications off, window 1440×900.
