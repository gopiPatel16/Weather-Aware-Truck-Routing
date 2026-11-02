# Weather-Aware Truck Routing

Helps a truck driver choose a safer route from **weather, cargo weight and travel time**. React + TypeScript frontend, Django REST backend, a truck-routing API, an hourly forecast API and a MapLibre map.

> **Status:** backend (276 tests, 96 % coverage) and frontend (80 tests) are complete and verified against the live TomTom and Open-Meteo APIs. Evidence for every requirement: [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md). Specification: [`docs/PLAN.md`](docs/PLAN.md). Provider evidence: [`docs/spike/SPIKE_REPORT.md`](docs/spike/SPIKE_REPORT.md). Measured numbers: [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md). Demo script: [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md).

**Live demo:** https://weather-aware-truck-routing-l7mt.onrender.com (free tier: the first visit after 15 minutes idle can take about a minute to wake up)

## What it does

1. You enter origin, destination, **departure date/time (in the origin's local time zone)**, **cargo weight (lb)** and a sampling interval of 10, 25 or 50 miles.
2. It asks the routing provider for **truck** routes and shows exactly the routes the provider returns (up to three) — it never invents routes.
3. It places a checkpoint every N miles, computes the truck's **ETA** at each from the route's travel-time data, and reads the forecast **interval that covers that ETA**.
4. It classifies risk with the assignment's wind/rain/snow thresholds and cargo-weight load rules.
5. It recommends the safest **eligible** route and explains why; it says so plainly when no route is safe or the forecast is incomplete.
6. A weather heatmap overview with a 0–48 h slider shows the corridor, while checkpoint markers and risk-coloured route segments give the exact categories.

## Risk rules (exactly as specified)

| Level | Wind (mph) | Rain (in/hr) | Snow (in/hr) |
|---|---|---|---|
| Low | < 25 | < 0.10 | < 0.5 |
| Moderate | 25 ≤ x < 35 | 0.10 ≤ x < 0.25 | 0.5 ≤ x < 1.0 |
| High | 35 ≤ x < 45 | 0.25 ≤ x < 0.50 | 1.0 ≤ x < 2.0 |
| Severe | 45 ≤ x < 55 | 0.50 ≤ x ≤ 1.00 | 2.0 ≤ x ≤ 3.0 |
| No Travel | x ≥ 55 | x > 1.00 | x > 3.0 |

*Boundary convention:* Low is below the first threshold; each later band includes its lower bound and excludes its upper bound; No Travel for rain/snow starts strictly above the printed Severe upper bound. Every exact boundary is tested.

*Load rules (cargo weight, strictly greater than):* wind ≥ 55 → No Travel for any load · wind 45–54 and > 30,000 lb → No Travel · wind 35–44 and > 40,000 lb → Severe. Final risk = the most severe of wind, rain, snow and the load rule. **Missing weather is Unknown, never Low.**

## Recommendation

- **Eligible** = no No-Travel miles **and** complete weather coverage (every route mile has a known risk). Both are shown per route.
- **Ranked** (eligible routes only): fewest Severe miles → fewest High miles → lowest average risk (distance-weighted, Low 0 … Severe 3) → shortest travel time.
- All routes blocked → **"No safe route available"** (nothing is labelled Recommended). Forecast incomplete → **"A safe recommendation cannot be determined"**.

## Assumptions and limitations

- Cargo weight is used only for the load rules; it is **not** sent to the routing API (the routing API's `vehicleWeight` means total vehicle weight). No axle/dimension/hazmat data is invented.
- ETAs assume continuous driving at the routing provider's truck speeds with typical traffic — no rest breaks or fuel stops. If the provider gives no timing data the ETAs are flagged "estimated from average speed".
- Only wind, rain and snow are modelled (no ice, fog or visibility). Wind means sustained 10 m speed (gusts are shown for information).
- Forecast reliability drops with lead time, so departure is limited to 7 days ahead. The app is US-unit based (mph, in/hr, lb).
- The free Open-Meteo API is for **non-commercial** use; commercial use needs a paid plan. It also allows about 600 locations per minute per IP, and every checkpoint and heatmap cell counts as one location. Several plans in a minute, or a 10-mile interval on a long trip, can exceed that. The server waits out a per-minute limit (up to about a minute); if the limit is hourly it reports that straight away. Anything it still cannot fetch becomes **Unknown** and the app says the recommendation cannot be determined instead of guessing. Repeat requests are cached for 30 minutes.
- TomTom answers take about 4–6 s for 1000-mile trips with alternatives, so a first plan takes roughly 6–10 s; repeats of the same trip are served in about a second.

## Run locally (Windows PowerShell)

Backend (needs a free TomTom key from [developer.tomtom.com](https://developer.tomtom.com), no credit card):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env        # then set TOMTOM_API_KEY in .env
.\.venv\Scripts\python manage.py runserver     # API on http://localhost:8000, docs at /api/docs/
.\.venv\Scripts\python -m pytest               # 276 tests
```

Frontend (Node 22.12+):

```powershell
cd frontend
npm ci
npm run dev          # http://localhost:5173, proxies /api to the backend
npm run dev:mock     # no backend: fixture scenarios with a picker in the header
npm run lint ; npm run typecheck ; npm test ; npm run build
```

More frontend detail (mock scenarios, pinned versions, accessibility): [`frontend/README.md`](frontend/README.md).

Notes:
- Without a TomTom key the API starts, but `/api/plan` answers "Routing is not configured". For a demo without real weather set `WEATHER_PROVIDER=mock` (synthetic storm, labelled as demo data).
- If HTTPS calls fail with `CERTIFICATE_VERIFY_FAILED` (antivirus or a proxy re-signing traffic), set `USE_SYSTEM_CA_STORE=1` in `backend/.env`. Certificate checks stay on; the operating system's trust store is used.
- Keys are read from the environment only and are never logged.

## Production image

`Dockerfile` builds the React app and serves it, together with the API, from one container (`gunicorn --workers 1 --threads 8`). `render.yaml` is a Render blueprint; set `TOMTOM_API_KEY` in the dashboard.

## API

`POST /api/plan` · `POST /api/heatmap` · `GET /api/geocode?q=` · `GET /api/health/` · OpenAPI at `/api/docs/`. Contract and examples: [`docs/PLAN.md`](docs/PLAN.md) §7 and [`docs/api-examples/`](docs/api-examples/).

## Hosting note

On Render's free tier the service sleeps after 15 minutes idle and the first request after that can take about a minute. No keep-alive trick is required; the app retries transient failures and tells the user what is happening.

## Attribution

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0) · Routing and search by TomTom · Map data © OpenStreetMap contributors, OpenMapTiles, OpenFreeMap.
