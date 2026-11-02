import type { Checkpoint, Route } from '../api/types';
import { RISK_STYLES, routeColor } from '../utils/risk';
import { levelRankForSort } from './rank';

export interface Fc<G, P> {
  type: 'FeatureCollection';
  features: { type: 'Feature'; geometry: G; properties: P }[];
}
type Line = { type: 'LineString'; coordinates: [number, number][] };
type Pt = { type: 'Point'; coordinates: [number, number] };

export interface RouteLineProps {
  id: string;
  color: string;
  selected: 0 | 1;
}
export interface SegmentProps {
  level: string;
}
export interface CheckpointProps {
  routeId: string;
  i: number;
  level: string;
  letter: string;
  radius: number;
  selected: 0 | 1;
  sortKey: number;
}

export function routeLines(routes: Route[], selectedId: string | null): Fc<Line, RouteLineProps> {
  return {
    type: 'FeatureCollection',
    features: routes.map((r, index) => ({
      type: 'Feature',
      geometry: r.geometry,
      properties: { id: r.id, color: routeColor(index), selected: r.id === selectedId ? 1 : 0 },
    })),
  };
}

/** Risk-coloured stretches of the selected route (each owned stretch carries its checkpoint's level). */
export function selectedSegments(route: Route | undefined): Fc<Line, SegmentProps> {
  return {
    type: 'FeatureCollection',
    features: (route?.segments ?? []).map((s) => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: s.coordinates },
      properties: { level: s.level },
    })),
  };
}

export function checkpointPoint(routeId: string, cp: Checkpoint, selected: boolean): CheckpointProps {
  const style = RISK_STYLES[cp.risk.level];
  return {
    routeId,
    i: cp.i,
    level: cp.risk.level,
    letter: style.letter,
    radius: style.radius,
    selected: selected ? 1 : 0,
    // Worst conditions are drawn on top where routes overlap; selected route above the rest.
    sortKey: levelRankForSort(cp.risk.level) + (selected ? 10 : 0),
  };
}

export function checkpointPoints(routes: Route[], selectedId: string | null): Fc<Pt, CheckpointProps> {
  return {
    type: 'FeatureCollection',
    features: routes.flatMap((r) =>
      r.checkpoints.map((cp) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [cp.lon, cp.lat] as [number, number] },
        properties: checkpointPoint(r.id, cp, r.id === selectedId),
      })),
    ),
  };
}
