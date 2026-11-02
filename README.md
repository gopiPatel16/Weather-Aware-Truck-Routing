# Weather-Aware Truck Routing

Helps a truck driver choose a safer route from **weather, cargo weight and travel time**. React + TypeScript frontend, Django REST backend, a truck-routing API, an hourly forecast API and a MapLibre map.

> **Build status** (details: [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md))
> Backend domain, weather client, planner and API are built and tested (254 tests, 98 % domain coverage). **Pending:** TomTom live verification (needs a free API key), the frontend, deployment, Loom.
> The full specification is [`docs/PLAN.md`](docs/PLAN.md); provider evidence is [`docs/spike/SPIKE_REPORT.md`](docs/spike/SPIKE_REPORT.md).

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
- The free Open-Meteo API is for **non-commercial** use; commercial use needs a paid plan.

## Run locally (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env        # then add TOMTOM_API_KEY (free, no card: developer.tomtom.com)
.\.venv\Scripts\python manage.py runserver     # http://localhost:8000/api/docs/
.\.venv\Scripts\python -m pytest               # tests
```
Without a TomTom key the API starts, but `/api/plan` answers "Routing is not configured". For a demo without real weather set `WEATHER_PROVIDER=mock` (synthetic storm, labelled as demo data).

## API

`POST /api/plan` · `POST /api/heatmap` · `GET /api/geocode?q=` · `GET /api/health/` · OpenAPI at `/api/docs/`. Contract and examples: [`docs/PLAN.md`](docs/PLAN.md) §7 and [`docs/api-examples/`](docs/api-examples/).

## Hosting note

On Render's free tier the service sleeps after 15 minutes idle and the first request after that can take about a minute. No keep-alive trick is required; the app retries transient failures and tells the user what is happening.

## Attribution

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0) · Routing and search by TomTom · Map data © OpenStreetMap contributors, OpenMapTiles, OpenFreeMap.
