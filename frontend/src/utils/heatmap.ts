import type { HeatmapResponse } from '../api/types';
import { HEAT_WEIGHTS, UNKNOWN_CODE, levelFromCode } from './risk';
import type { RiskLevel } from '../api/types';

export const HEATMAP_HOURS = 49;

/** All 49 hours of every cell, preloaded once: `levels[cell * hours + hour]` (0–4 known, 9 unknown). */
export interface HeatmapData {
  cellCount: number;
  hours: number;
  startUtc: string;
  lats: Float64Array;
  lons: Float64Array;
  levels: Uint8Array;
  cellMiles: number;
  halfWidthMiles: number;
  warnings: string[];
}

export function decodeHeatmap(resp: HeatmapResponse): HeatmapData {
  const hours = resp.hours || HEATMAP_HOURS;
  const n = resp.cells.length;
  const lats = new Float64Array(n);
  const lons = new Float64Array(n);
  const levels = new Uint8Array(n * hours).fill(UNKNOWN_CODE);
  resp.cells.forEach((cell, i) => {
    lats[i] = cell.lat;
    lons[i] = cell.lon;
    const s = cell.levels;
    for (let h = 0; h < hours && h < s.length; h++) {
      const code = s.charCodeAt(h) - 48;
      levels[i * hours + h] = code >= 0 && code <= 4 ? code : UNKNOWN_CODE;
    }
  });
  return {
    cellCount: n,
    hours,
    startUtc: resp.start_utc,
    lats,
    lons,
    levels,
    cellMiles: resp.cell_miles,
    halfWidthMiles: resp.half_width_miles,
    warnings: resp.meta.warnings ?? [],
  };
}

export const hourProp = (hour: number): string => `h${hour}`;

/** MapLibre `match` expression turning the per-hour level property into a heat weight. */
export function weightExpression(hour: number) {
  const get = ['get', hourProp(hour)];
  return [
    'match',
    get,
    0,
    HEAT_WEIGHTS.low,
    1,
    HEAT_WEIGHTS.moderate,
    2,
    HEAT_WEIGHTS.high,
    3,
    HEAT_WEIGHTS.severe,
    4,
    HEAT_WEIGHTS.no_travel,
    0,
  ];
}

/** Opacity expression: 1 for Unknown cells at the hour (hollow grey dot), 0 otherwise. */
export function unknownOpacityExpression(hour: number) {
  return ['case', ['==', ['get', hourProp(hour)], UNKNOWN_CODE], 1, 0];
}

export interface HeatFeatureCollection {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    geometry: { type: 'Point'; coordinates: [number, number] };
    properties: Record<string, number>;
  }[];
}

/** One point per cell carrying all hours as `h0…h48` so scrubbing only swaps paint expressions. */
export function toFeatureCollection(data: HeatmapData): HeatFeatureCollection {
  const features: HeatFeatureCollection['features'] = [];
  for (let i = 0; i < data.cellCount; i++) {
    const properties: Record<string, number> = {};
    for (let h = 0; h < data.hours; h++)
      properties[hourProp(h)] = data.levels[i * data.hours + h] ?? UNKNOWN_CODE;
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [data.lons[i] ?? 0, data.lats[i] ?? 0] },
      properties,
    });
  }
  return { type: 'FeatureCollection', features };
}

/** Number of cells per level at an hour (for the legend counts and tests). */
export function countLevelsAtHour(data: HeatmapData, hour: number): Record<RiskLevel, number> {
  const counts: Record<RiskLevel, number> = {
    low: 0,
    moderate: 0,
    high: 0,
    severe: 0,
    no_travel: 0,
    unknown: 0,
  };
  for (let i = 0; i < data.cellCount; i++) {
    counts[levelFromCode(data.levels[i * data.hours + hour] ?? UNKNOWN_CODE)] += 1;
  }
  return counts;
}
