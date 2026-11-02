/** Types for the API contract in docs/PLAN.md §7. */

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel' | 'unknown';
export type KnownRiskLevel = Exclude<RiskLevel, 'unknown'>;

export type EtaMethod = 'route_guidance' | 'estimated_uniform_speed';
export type RecommendationStatus = 'recommended' | 'no_safe_route' | 'inconclusive';
export type IneligibleReason = 'no_travel' | 'incomplete_weather';
export type IntervalMiles = 10 | 25 | 50;

export interface PlaceRef {
  label: string;
  lat: number;
  lon: number;
}

export interface GeocodeResult extends PlaceRef {
  /** IANA zone computed offline by the backend. */
  timezone: string;
}

export interface GeocodeResponse {
  results: GeocodeResult[];
}

export interface PlanRequest {
  origin: PlaceRef;
  destination: PlaceRef;
  /** Naive `YYYY-MM-DDTHH:MM`, interpreted in the ORIGIN's time zone (never the browser's). */
  departure_local: string;
  cargo_weight_lb: number;
  interval_miles: IntervalMiles;
}

export interface PlanRequestEcho {
  origin_timezone: string;
  departure_local: string;
  departure_utc: string;
  interval_miles: number;
  /** Present in the backend's fixtures; not in PLAN §7. */
  requested_interval_miles?: number;
  interval_adjusted: boolean;
  cargo_weight_lb: number;
  warnings: string[];
}

export interface AlternativesInfo {
  requested: number;
  returned: number;
  usable: number;
  message: string;
}

export interface RouteSegment {
  from_mi: number;
  to_mi: number;
  level: RiskLevel;
  coordinates: [number, number][];
}

export interface MilesByLevel {
  low: number;
  moderate: number;
  high: number;
  severe: number;
  no_travel: number;
  unknown: number;
}

export interface RouteSummary {
  miles_by_level: MilesByLevel;
  coverage_pct: number;
  no_travel_mi: number;
  severe_mi: number;
  high_mi: number;
  avg_risk: number | null;
  max_level: RiskLevel;
  checkpoint_count: number;
}

export interface Eligibility {
  eligible: boolean;
  reasons: IneligibleReason[];
}

export interface WeatherBasis {
  precip_intervals: [string, string][];
  wind_stamps: string[];
  adjacent_interval_used: boolean;
}

export interface CheckpointWeather {
  wind_mph: number | null;
  gust_mph: number | null;
  rain_in_hr: number | null;
  snow_in_hr: number | null;
  temp_f: number | null;
  basis: WeatherBasis;
  source_units: { wind: string; rain: string; snow: string };
}

export interface RiskDriver {
  factor: string;
  level: RiskLevel;
  text: string;
}

export interface CheckpointRisk {
  level: RiskLevel;
  score: number | null;
  at_least: RiskLevel | null;
  missing: string[];
  drivers: RiskDriver[];
}

export interface Checkpoint {
  i: number;
  mile: number;
  lat: number;
  lon: number;
  eta_utc: string;
  tz: string;
  /** `null` when the forecast for this checkpoint is unavailable (risk is then Unknown). */
  weather: CheckpointWeather | null;
  risk: CheckpointRisk;
}

export interface Route {
  id: string;
  name: string;
  via: string | null;
  distance_mi: number;
  duration_s: number;
  arrival_utc: string;
  arrival_tz: string;
  eta_method: EtaMethod;
  geometry: { type: 'LineString'; coordinates: [number, number][] };
  /** Precision-5 encoded display geometry; posted back unchanged to /api/heatmap. */
  polyline: string;
  segments: RouteSegment[];
  summary: RouteSummary;
  eligibility: Eligibility;
  checkpoints: Checkpoint[];
}

export interface Recommendation {
  status: RecommendationStatus;
  route_id: string | null;
  ranking: string[];
  headline: string;
  reasons: string[];
  caveats: string[];
}

export interface PlanMeta {
  routing_provider: string;
  weather_provider: string;
  weather_model: string;
  timings_ms: Record<string, number>;
  weather_cache: { hits: number; misses: number };
}

export interface PlanResponse {
  request: PlanRequestEcho;
  alternatives: AlternativesInfo;
  routes: Route[];
  recommendation: Recommendation;
  meta: PlanMeta;
}

export interface HeatmapRequest {
  routes: { id: string; polyline: string }[];
  departure_utc: string;
  cargo_weight_lb: number;
}

export interface HeatmapCell {
  lat: number;
  lon: number;
  /** 49 characters (hour 0…48): `0`–`4` known level, `9` unknown. */
  levels: string;
}

export interface HeatmapResponse {
  start_utc: string;
  hours: number;
  cell_miles: number;
  half_width_miles: number;
  cells: HeatmapCell[];
  meta: {
    cells: number;
    unknown_cells: number;
    warnings?: string[];
    timings_ms?: Record<string, number>;
  };
}

export type ErrorCode =
  | 'validation_error'
  | 'invalid_departure_time'
  | 'no_route'
  | 'trip_too_long'
  | 'rate_limited'
  | 'routing_unavailable'
  | 'weather_unavailable'
  | 'quota_exceeded'
  | (string & {});

export interface ApiErrorBody {
  error: {
    code: ErrorCode;
    message: string;
    retry_after_s?: number;
    /** Per-field messages on `validation_error` (present in the backend's fixtures). */
    fields?: Record<string, string[]>;
  };
}
