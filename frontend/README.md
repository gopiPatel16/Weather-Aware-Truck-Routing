# Frontend — Weather-Aware Truck Routing

React + TypeScript + Vite + Tailwind CSS, with plain `maplibre-gl` behind a thin lifecycle wrapper.
It follows the API contract in [`docs/PLAN.md`](../docs/PLAN.md) §7 and the UI plan in §8 / §6.

## Run it

```powershell
cd frontend
npm ci

npm run dev          # http://localhost:5173 — proxies /api to http://localhost:8000 (the Django backend)
npm run dev:mock     # same, but /api is answered from mock/ fixtures (no backend needed)
```

`VITE_USE_MOCK=1 npm run dev` is equivalent to `npm run dev:mock` (on Windows PowerShell:
`$env:VITE_USE_MOCK = "1"; npm run dev`).

| Script              | What it does                                           |
| ------------------- | ------------------------------------------------------ |
| `npm run lint`      | ESLint (typescript-eslint, react-hooks)                |
| `npm run typecheck` | `tsc -b --noEmit` (strict, `noUncheckedIndexedAccess`) |
| `npm test`          | Vitest + Testing Library (jsdom)                       |
| `npm run build`     | typecheck + production build into `dist/`              |
| `npm run format`    | Prettier                                               |

### Environment

| Variable             | Default                                         | Purpose                                      |
| -------------------- | ----------------------------------------------- | -------------------------------------------- |
| `VITE_MAP_STYLE_URL` | `https://tiles.openfreemap.org/styles/positron` | Basemap style JSON (build-time)              |
| `VITE_USE_MOCK`      | unset                                           | `1` serves fixtures instead of the backend   |
| `VITE_API_TARGET`    | `http://localhost:8000`                         | Dev-server proxy target for `/api`           |
| `VITE_API_BASE`      | empty (same origin)                             | Prefix for API calls if the API is elsewhere |

The OpenFreeMap style currently carries source attributions; if a style has none, the map adds
"© OpenStreetMap contributors · © OpenMapTiles · OpenFreeMap" itself. The footer also credits
"Weather data by Open-Meteo.com" and "Routing © TomTom".

## Mock mode

`mock/fixtures/*.json` are copies of the backend pipeline's real output (`docs/api-examples/`) plus
`heatmap_unknown.json` (derived with `node mock/make-heatmap-unknown.mjs`: whole cells and late hours are `9`).
`mock/install.ts` replaces `window.fetch` for `/api/*` with simulated latency (plan 1.8 s, heatmap 0.7 s), and a
**MOCK** scenario picker appears in the header (it can also be preset with `?scenario=<id>`):

| Scenario                                                  | Shows                                                                                                        |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `normal`                                                  | 3 routes; Moderate/High/Severe checkpoints, load-rule drivers, B has No Travel → C recommended               |
| `calm`                                                    | 3 routes, all Low                                                                                            |
| `two_routes`                                              | only 2 routes → "returned 2 valid alternatives" message                                                      |
| `one_route`                                               | 1 route → "returned no alternative routes"                                                                   |
| `no_safe_route`                                           | every route has No Travel miles → "No safe route available", no ★                                            |
| `inconclusive`                                            | Unknown checkpoints, coverage 52–56 % → "A safe recommendation cannot be determined"; heatmap with `9` cells |
| `estimated_eta`                                           | `estimated_uniform_speed` ETA flag                                                                           |
| `cold_start`                                              | 503 twice then OK → visible "server is starting up or busy" retry (2 s, 5 s)                                 |
| `routing_error`                                           | 502 + `retry_after_s` on every call → retries exhausted → manual Retry                                       |
| `rate_limited` / `validation_error` / `invalid_departure` | the backend's error envelopes (no auto retry)                                                                |
| `heatmap_failed`                                          | plan OK, heatmap 502 → routes stay usable, "Retry heatmap"                                                   |

The mock honours the submitted cargo weight and `interval_miles = 50` (it thins the 25-mi fixture checkpoints);
10 mi adds a "mock data is fixed at 25 mi" warning. Mock code is loaded with a dynamic import, so it is **not** in
production bundles.

## Layout of `src/`

```
api/         types.ts (PLAN §7) · client.ts (typed fetch + AbortController) · retry.ts (2/5/10 s) · errors.ts
state/       usePlanner (plan request, retry state) · useHeatmap (one heatmap request per plan)
components/  TripForm, PlaceInput (combobox), RecommendationBanner, PlanNotices, RouteCard, RiskStrip,
             CheckpointTable, RulesDrawer, HeatmapPanel, TimeSlider, Legend, MapView, StatusPanels
map/         MapController.ts (lifecycle wrapper: sources, layers, markers, popup, rAF-coalesced hour updates),
             sources.ts (GeoJSON builders), popup.ts (DOM-built popup), geometry.ts
utils/       format (Intl time-zone formatting), risk (levels, colours, glyphs, heat weights), validation, time,
             heatmap (decode / weight expressions), forecast, rules
```

### Behaviour worth knowing

- **Departure time** is a naive `YYYY-MM-DDTHH:MM` read in the **origin's** zone (shown beside the field,
  e.g. `America/Chicago · CST`). The browser's zone is never used; validation windows are computed in the origin zone.
- **Each checkpoint ETA** is formatted with `Intl` in that checkpoint's own IANA zone, with the abbreviation.
- **Risk is never colour-only:** badges and the legend carry a glyph and a label, map markers carry a letter and a
  size, `Unknown` is a hollow grey ring / dashed grey segment, `No Travel` strips are hatched.
- **Heatmap:** all 49 hours arrive in one response and are decoded into a single `Uint8Array`
  (`cell × 49 + hour`). Each cell becomes one GeoJSON point with properties `h0…h48`; moving the slider only swaps two
  paint expressions (`heatmap-weight`, hollow-dot opacity) in one `requestAnimationFrame`, so **no request is made
  while scrubbing** (asserted in `App.test.tsx` and `TimeSlider.test.tsx`). The heat layer sits below the basemap
  labels, is labelled _"Smoothed forecast overview at slider time"_, and the legend states that markers and route
  colours are the exact categories. Autoplay is disabled under `prefers-reduced-motion`.
- **Mobile (< 900 px):** the results panel becomes a bottom sheet (peek / half / full) under the map.
- **Dev aid:** in `npm run dev` the MapLibre instance is exposed as `window.__map`.

## Dependency versions and compatibility

All versions are pinned exactly in `package.json` (checked with `npm view <pkg> peerDependencies`, `npm ls`, the
full test run and a production build):

| Package                              | Pinned                                                                                           | Note                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vite`                               | 8.3.5                                                                                            | `@vitejs/plugin-react@6.1.2` (peer `vite ^8`), `@tailwindcss/vite@4.3.3` (`^5.2 … ^8`) and `vitest@5.0.5` (`^6.4 … ^8`) all accept it                                                                                                                                                                                                                                                                                                                                             |
| `typescript`                         | 6.0.3                                                                                            | **Not 7.** `typescript-eslint@8.72.1` declares `typescript >=4.8.4 <6.1.0`; 6.0.x is the newest release inside that range                                                                                                                                                                                                                                                                                                                                                         |
| `eslint` / `@eslint/js`              | 10.14.0 / 10.0.1                                                                                 | `typescript-eslint` and `eslint-plugin-react-hooks@7.1.1` list ESLint 10                                                                                                                                                                                                                                                                                                                                                                                                          |
| `react` / `react-dom`                | 19.3.1                                                                                           | `react-dom` peers `react ^19.3.1`; `@types/react(-dom)` 19.3.0; Testing Library 16.3.3 supports React 19                                                                                                                                                                                                                                                                                                                                                                          |
| `tailwindcss`                        | 4.3.3                                                                                            | via the first-party Vite plugin (no PostCSS config)                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `maplibre-gl`                        | 6.16.0                                                                                           | newest major, verified by building and driving the map in dev and production. **One caveat:** MapLibre 6 finds its worker with `new URL(…, import.meta.url)`, which fails once Vite chunks/pre-bundles the library (production: HTML returned for the worker URL, dev: "Worker failed to load"). `MapView` therefore imports `maplibre-gl/dist/maplibre-gl-worker.mjs?url` and calls `setWorkerUrl()` explicitly. If that ever proves brittle, MapLibre 5.x is the fallback major |
| `vitest` / `jsdom` / Testing Library | 5.0.5 / 30.1.1 / 16.3.3 (+ `@testing-library/dom` 10.4.2, `jest-dom` 7.0.1, `user-event` 14.6.5) | `jest-dom` peers `@testing-library/dom >=10 <11`                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `prettier`                           | 3.9.6                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

Requires Node ≥ 22.12 (Vite 8); developed on Node 24 / npm 11.

## Bundle

Initial JS ≈ 85 KB gzip (target < 150 KB). MapLibre (≈ 298 KB gzip) and the map controller are separate lazy chunks
loaded after first paint; the MapLibre worker is a separate asset.

## Accessibility notes

Labelled inputs; origin/destination are ARIA 1.2 comboboxes (Up/Down/Enter/Esc, `aria-activedescendant`,
live "N suggestions" / "No match" text); the slider is a native `<input type="range">` with `aria-valuetext`
("+12 h: Mon, Nov 2, 6:00 PM CST (America/Chicago)"); results are inside an `aria-live` region; the Rules drawer is a
native `<dialog>` (focus trap, Esc); focus rings are always visible; badge text colours meet AA contrast against
their tints (asserted in `risk.test.ts`); route chips on the map are real buttons, and every checkpoint is also
reachable from the keyboard through the checkpoint table.
