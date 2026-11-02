import type { GeocodeResult, HeatmapResponse, PlanResponse } from '../api/types';
import planStorm from '../../mock/fixtures/plan_storm.json';
import planTwoRoutes from '../../mock/fixtures/plan_two_routes.json';
import planNoSafe from '../../mock/fixtures/plan_no_safe_route.json';
import planInconclusive from '../../mock/fixtures/plan_inconclusive.json';
import planEstimated from '../../mock/fixtures/plan_estimated_eta.json';
import heatmapStorm from '../../mock/fixtures/heatmap_storm.json';
import heatmapUnknown from '../../mock/fixtures/heatmap_unknown.json';

const clone = <T>(x: unknown): T => structuredClone(x) as T;

export const storm = () => clone<PlanResponse>(planStorm);
export const twoRoutes = () => clone<PlanResponse>(planTwoRoutes);
export const noSafeRoute = () => clone<PlanResponse>(planNoSafe);
export const inconclusive = () => clone<PlanResponse>(planInconclusive);
export const estimatedEta = () => clone<PlanResponse>(planEstimated);
export const heatmap = () => clone<HeatmapResponse>(heatmapStorm);
export const heatmapWithUnknown = () => clone<HeatmapResponse>(heatmapUnknown);

export const CHICAGO: GeocodeResult = {
  label: 'Chicago, IL, USA',
  lat: 41.8781,
  lon: -87.6298,
  timezone: 'America/Chicago',
};
export const DENVER: GeocodeResult = {
  label: 'Denver, CO, USA',
  lat: 39.7392,
  lon: -104.9903,
  timezone: 'America/Denver',
};

export const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
