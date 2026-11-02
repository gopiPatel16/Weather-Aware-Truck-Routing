"""Tunable constants. Each one is explained in docs/PLAN.md (section numbers in comments)."""

from datetime import timedelta

# --- request validation (plan 5.8, D13) ---------------------------------------------------
INTERVAL_OPTIONS = (10, 25, 50)  # miles between weather checkpoints
DEFAULT_INTERVAL_MILES = 25
MAX_CHECKPOINTS_PER_ROUTE = 300
MIN_ROUTE_MILES = 5.0
MAX_ROUTE_MILES = 3500.0
MAX_CARGO_LB = 150_000
DEPARTURE_GRACE = timedelta(minutes=15)
MAX_DEPARTURE_AHEAD = timedelta(days=7)

# --- geometry (plan 5.2) ------------------------------------------------------------------
GEOMETRY_MIN_SPACING_M = 50.0  # decimation spacing before distance maths
DISPLAY_SIMPLIFY_TOLERANCE_M = 100.0  # Douglas-Peucker tolerance for geometry sent to the browser

# --- route alternatives (plan 5.1) --------------------------------------------------------
ROUTES_REQUESTED = 3
DUPLICATE_SHARE = 0.95  # both directions
DUPLICATE_WITHIN_MILES = 0.5
DUPLICATE_METRIC_TOLERANCE = 0.03  # 3 % distance and duration

# --- forecast-interval policy (plan 5.4) --------------------------------------------------
ADJACENT_MARGIN = timedelta(minutes=15)
HEATMAP_HOURS = 48  # slider 0..48 -> 49 positions

# --- coverage rule (plan 5.7, D6) ---------------------------------------------------------
MIN_COVERAGE_FOR_RECOMMENDATION = 1.0  # every route mile must have a known risk

# --- weather client (plan 5.3) ------------------------------------------------------------
WEATHER_COORD_DECIMALS = 2  # about 1 km
WEATHER_CHUNK_SIZE = 100
WEATHER_PARALLEL_REQUESTS = 6
WEATHER_FORECAST_LIMIT_DAYS = 15  # Open-Meteo rejects end_hour beyond today + 15 days
WEATHER_CACHE_TTL_S = 30 * 60
ROUTING_CACHE_TTL_S = 15 * 60
GEOCODE_CACHE_TTL_S = 60 * 60

# --- heatmap (plan 6) ---------------------------------------------------------------------
HEATMAP_CELL_MILES = 15.0
HEATMAP_HALF_WIDTH_MILES = 20.0
HEATMAP_ROUTE_SAMPLE_MILES = 5.0
