import type {
  ApiErrorBody,
  GeocodeResult,
  HeatmapResponse,
  PlanRequest,
  PlanResponse,
} from '../src/api/types';
import planStorm from './fixtures/plan_storm.json';
import planCalm from './fixtures/plan_calm.json';
import planTwoRoutes from './fixtures/plan_two_routes.json';
import planNoSafeRoute from './fixtures/plan_no_safe_route.json';
import planInconclusive from './fixtures/plan_inconclusive.json';
import planEstimatedEta from './fixtures/plan_estimated_eta.json';
import heatmapStorm from './fixtures/heatmap_storm.json';
import heatmapUnknown from './fixtures/heatmap_unknown.json';
import errInvalidDeparture from './fixtures/error_invalid_departure.json';
import errRateLimited from './fixtures/error_rate_limited.json';
import errRouting from './fixtures/error_routing_unavailable.json';
import errValidation from './fixtures/error_validation.json';

/**
 * Mock scenarios, backed by the backend's real pipeline output (docs/api-examples, copied to
 * mock/fixtures). Each scenario decides what /api/plan and /api/heatmap return.
 */
export const SCENARIO_IDS = [
  'normal',
  'calm',
  'two_routes',
  'one_route',
  'no_safe_route',
  'inconclusive',
  'estimated_eta',
  'cold_start',
  'routing_error',
  'rate_limited',
  'validation_error',
  'invalid_departure',
  'heatmap_failed',
] as const;
export type ScenarioId = (typeof SCENARIO_IDS)[number];

export const SCENARIO_LABELS: Record<ScenarioId, string> = {
  normal: '3 routes · Moderate/High/Severe + load rule',
  calm: '3 routes · all Low',
  two_routes: '2 routes only (alternatives message)',
  one_route: '1 route only',
  no_safe_route: 'No safe route (all No Travel)',
  inconclusive: 'Inconclusive (Unknown, coverage < 100 %)',
  estimated_eta: 'Estimated ETA (uniform speed)',
  cold_start: 'Cold start (503 ×2, then OK)',
  routing_error: 'Routing error 502 (retry_after_s)',
  rate_limited: 'Rate limited 429',
  validation_error: 'Validation error 400',
  invalid_departure: 'Invalid departure (DST gap) 400',
  heatmap_failed: 'Plan OK, heatmap fails',
};

export interface MockReply {
  status: number;
  body: unknown;
}

const asPlan = (x: unknown): PlanResponse => structuredClone(x) as PlanResponse;
const asError = (x: unknown): ApiErrorBody => structuredClone(x) as ApiErrorBody;

function oneRoute(): PlanResponse {
  const plan = asPlan(planCalm);
  const only = plan.routes.slice(0, 1);
  plan.routes = only;
  plan.alternatives = {
    requested: 3,
    returned: 1,
    usable: 1,
    message: 'The routing provider returned no alternative routes for this trip.',
  };
  plan.recommendation = {
    status: 'recommended',
    route_id: 'A',
    ranking: ['A'],
    headline: 'Route A is the only available route',
    reasons: ['Route A is the only route the provider returned, and it is eligible'],
    caveats: [],
  };
  return plan;
}

function basePlan(id: ScenarioId): PlanResponse {
  switch (id) {
    case 'calm':
      return asPlan(planCalm);
    case 'two_routes':
      return asPlan(planTwoRoutes);
    case 'one_route':
      return oneRoute();
    case 'no_safe_route':
      return asPlan(planNoSafeRoute);
    case 'inconclusive':
      return asPlan(planInconclusive);
    case 'estimated_eta':
      return asPlan(planEstimatedEta);
    default:
      return asPlan(planStorm);
  }
}

/** Echo the submitted settings back; the fixtures themselves are sampled every 25 mi. */
function applyRequest(plan: PlanResponse, req: PlanRequest | null): PlanResponse {
  if (!req) return plan;
  plan.request.cargo_weight_lb = req.cargo_weight_lb;
  plan.request.departure_local = req.departure_local;
  if (req.interval_miles === 50) {
    for (const route of plan.routes) {
      const last = route.checkpoints.length - 1;
      route.checkpoints = route.checkpoints.filter((c, i) => c.mile % 50 === 0 || i === last);
      route.summary.checkpoint_count = route.checkpoints.length;
    }
    plan.request.interval_miles = 50;
  } else if (req.interval_miles === 10) {
    plan.request.warnings = [...plan.request.warnings, 'Mock data: checkpoints are fixed at 25 mi spacing.'];
  }
  return plan;
}

export interface ScenarioState {
  /** Number of /api/plan calls served in the current scenario (drives `cold_start`). */
  planCalls: number;
}

export function planReply(id: ScenarioId, req: PlanRequest | null, state: ScenarioState): MockReply {
  state.planCalls += 1;
  switch (id) {
    case 'cold_start':
      return state.planCalls <= 2
        ? { status: 503, body: asError(errRouting) }
        : { status: 200, body: applyRequest(basePlan('normal'), req) };
    case 'routing_error':
      return { status: 502, body: asError(errRouting) };
    case 'rate_limited':
      return { status: 429, body: asError(errRateLimited) };
    case 'validation_error':
      return { status: 400, body: asError(errValidation) };
    case 'invalid_departure':
      return { status: 400, body: asError(errInvalidDeparture) };
    default:
      return { status: 200, body: applyRequest(basePlan(id), req) };
  }
}

/** Heatmap payload whose every cell is the same level code, so overview and markers agree in uniform scenarios. */
function uniform(source: unknown, code: string): HeatmapResponse {
  const resp = structuredClone(source) as unknown as HeatmapResponse;
  resp.cells = resp.cells.map((c) => ({ ...c, levels: code.repeat(49) }));
  return resp;
}

export function heatmapReply(id: ScenarioId): MockReply {
  switch (id) {
    case 'heatmap_failed':
      return {
        status: 502,
        body: {
          error: {
            code: 'weather_unavailable',
            message: 'The weather forecast service is unavailable right now.',
          },
        },
      };
    case 'inconclusive':
      return { status: 200, body: structuredClone(heatmapUnknown) as unknown as HeatmapResponse };
    case 'no_safe_route':
      return { status: 200, body: uniform(heatmapStorm, '4') };
    case 'calm':
    case 'estimated_eta':
      return { status: 200, body: uniform(heatmapStorm, '0') };
    default:
      return { status: 200, body: structuredClone(heatmapStorm) as unknown as HeatmapResponse };
  }
}

const CITIES: GeocodeResult[] = [
  { label: 'Chicago, IL, USA', lat: 41.8781, lon: -87.6298, timezone: 'America/Chicago' },
  { label: 'Denver, CO, USA', lat: 39.7392, lon: -104.9903, timezone: 'America/Denver' },
  { label: 'Dallas, TX, USA', lat: 32.7767, lon: -96.797, timezone: 'America/Chicago' },
  { label: 'Atlanta, GA, USA', lat: 33.749, lon: -84.388, timezone: 'America/New_York' },
  { label: 'Seattle, WA, USA', lat: 47.6062, lon: -122.3321, timezone: 'America/Los_Angeles' },
  { label: 'Salt Lake City, UT, USA', lat: 40.7608, lon: -111.891, timezone: 'America/Denver' },
  { label: 'Omaha, NE, USA', lat: 41.2565, lon: -95.9345, timezone: 'America/Chicago' },
  { label: 'New York, NY, USA', lat: 40.7128, lon: -74.006, timezone: 'America/New_York' },
  { label: 'Phoenix, AZ, USA', lat: 33.4484, lon: -112.074, timezone: 'America/Phoenix' },
  { label: 'Denton, TX, USA', lat: 33.2148, lon: -97.1331, timezone: 'America/Chicago' },
];

export function geocodeReply(q: string): MockReply {
  const needle = q.trim().toLowerCase();
  return { status: 200, body: { results: CITIES.filter((c) => c.label.toLowerCase().includes(needle)) } };
}
