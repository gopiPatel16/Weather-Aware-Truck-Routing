# Measured performance

Everything here was measured on 2 Nov 2026 on the development PC (Windows 10, Python 3.12, Django dev server, residential network) against the **live** TomTom and Open-Meteo APIs, except where noted. Targets come from `docs/PLAN.md` §11.

## Plan endpoint (`POST /api/plan`, 3 routes, 42,000 lb)

Server-side timings are the `meta.timings_ms` the API itself reports. Trips were run one at a time with a pause between them so Open-Meteo's free rate limit did not distort the result.

| Trip | Interval | Checkpoints (3 routes) | Payload | Cold, server `total` | Warm, server `total` |
|---|---|---|---|---|---|
| Chicago → Denver | 10 mi | — | 256 KB | 9.3 s (routing 4.7 s, weather 4.0 s) | — |
| Chicago → Denver | 25 mi | 41 / 47 / 54 | 144 KB | 1.8 s* | 0.54 s |
| Chicago → Denver | 50 mi | — | 108 KB | 0.55 s* | — |
| Dallas → Atlanta | 25 mi | — | 120 KB | 5.7 s (routing 4.2 s, weather 1.0 s) | — |
| Seattle → Salt Lake City | 25 mi | — | 152 KB | 6.7 s (routing 5.1 s, weather 1.1 s) | — |
| Minneapolis → Billings | 25 mi | — | 144 KB | 5.9 s (routing 4.3 s, weather 1.1 s) | — |

\* these ran after the same trip had already been planned at another interval, so routing and part of the weather came from cache.

- **Cold target < 6 s: mostly met, not always.** TomTom itself takes 4–5 s for ~1000-mile trips with alternatives (3.9–5.6 s in the spike), which is most of the cold time. Cold plans measured 5.7–6.7 s at 25 mi.
- **Warm target < 1.5 s: met** (0.54 s measured for Chicago → Denver at 25 mi). A repeat of the same trip within the cache window (routing 15 min, weather 30 min) is served in about half a second. Before optimisation a warm plan took 4.3 s; profiling showed the route-simplification step (Douglas–Peucker) taking ~3.5 s of it, so it was rewritten to project points once and compare squared distances (now ≈ 0.4 s for three routes).
- Wall-clock times from a client on this PC were about 2 s longer than the server's own numbers. That is the Windows `localhost` → IPv6 fallback delay, not the app (`127.0.0.1` showed 0.55 s end to end).

## Heatmap endpoint (`POST /api/heatmap`)

| Trip (25 mi plan) | Cells | Unknown cells | Payload |
|---|---|---|---|
| Chicago → Denver | 584–585 | 0 | 53 KB |
| Dallas → Atlanta | 379–380 | 0 | 34 KB |
| Seattle → Salt Lake City | 447–448 | 0 | 41 KB |
| Minneapolis → Billings | 502–503 | 0 (287 in one run that hit the Open-Meteo rate limit) | 46 KB |

- Cells are 15 mi apart in real distance with a 20 mi half-width around every returned route, so a realistic corridor is **380–590 cells and 34–53 KB** for all 49 hours.
- Warm: ≈ 1.8 s for 585 cells (49 hours × 585 cells ≈ 28,700 risk assessments in pure Python). Cold: roughly 3.5–4.5 s server-side (client-side 5.3–6.6 s including the localhost delay above). The page shows the routes immediately and the slider card says "Loading forecast overview…" until this arrives; a failure leaves the routes usable.

## Front end

| Item | Target | Result |
|---|---|---|
| Initial JavaScript | < 150 KB gzip before the map chunk | **85 KB gzip** (`index` chunk); MapLibre (298 KB gzip), the map controller (4.7 KB) and the MapLibre worker (a separate 519 KB asset) load afterwards |
| Slider makes no request while scrubbing | 0 | **0**, asserted in `App.test.tsx` and `TimeSlider.test.tsx`; all 49 hours of every cell sit in one `Uint8Array` |
| Cost of one slider step | well under a frame | The main thread spends **0.2 ms median, 0.4 ms p95, 1.9 ms max** per step (two paint-property swaps on a 585-point source; 196 steps measured in Chromium). Updates are coalesced to at most one per animation frame |
| Slider/play ≥ 55 fps | measured with a frame probe | **Not measured end to end.** The in-app browser pauses animation frames while its pane is hidden, so a frame-time probe could not run. The per-step cost above leaves most of the 16.7 ms frame budget free; please confirm by eye or with the browser's Performance panel |
| Lighthouse ≥ 90 (desktop, hosted page) | measured | **Performance 78 (target not met)**, Accessibility 100, Best practices 100. FCP 0.6 s, LCP 0.6 s, CLS 0.003, speed index 1.8 s, total blocking time 420 ms. The blocking time is almost entirely evaluating the MapLibre bundle (about 0.7 s of scripting, one 390 ms task), which the map needs to draw anything; the app's own script is 70 ms. Not tuned further |

## Provider limits seen in practice

Open-Meteo's free tier allows about 600 locations per minute per IP, and every checkpoint and heatmap cell counts as one. Two to three plans at a 10-mile interval inside a minute exceeded it; the API then answered HTTP 429 for some chunks. The app's behaviour was correct and honest: the affected checkpoints became **Unknown**, coverage dropped below 100 %, the banner said "A safe recommendation cannot be determined", and when every chunk failed the API returned 502 `weather_unavailable` with `retry_after_s`. Results are cached for 30 minutes, which makes repeat requests free.

## Hosted app (Render free tier), 2 Nov 2026

URL: https://weather-aware-truck-routing-l7mt.onrender.com

| Check | Result |
|---|---|
| `/api/health/` | 200, about 0.9 s |
| `GET /api/geocode?q=Chicago` | TomTom suggestions with time zones |
| `POST /api/plan` Chicago → Denver, 25 mi | 3 routes, `route_guidance` ETAs, 100 % coverage, **6.5 s** end to end (routing 3.4 s, weather 0.9 s) |
| `POST /api/heatmap` for that plan | 585 cells, 0 Unknown, 54 KB, **14–19 s** (weather 6–8 s; the free instance has a fraction of a CPU, so the pure-Python risk pass for 585 × 49 values is the rest). The slider card shows "Loading forecast overview…" meanwhile and the routes are usable |
| Browser, real data | form → recommendation banner → three route cards with real Severe/High miles |
| **Cold start** (17 min with no traffic, then one request) | First request **200 in 14.5 s** (the app page), next request 0.9 s. Render's documentation says up to about a minute; 14.5 s was measured once |
