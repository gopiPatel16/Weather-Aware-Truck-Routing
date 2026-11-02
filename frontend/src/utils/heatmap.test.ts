import { describe, expect, it } from 'vitest';
import { heatmap, heatmapWithUnknown } from '../test/fixtures';
import {
  HEATMAP_HOURS,
  countLevelsAtHour,
  decodeHeatmap,
  hourProp,
  toFeatureCollection,
  unknownOpacityExpression,
  weightExpression,
} from './heatmap';
import { heatWeightForCode } from './risk';
import { etaHourOffset, nowInZone, departureWindow, nextFullHour } from './time';

describe('heatmap decoding', () => {
  it('preloads all 49 hours of every cell into one Uint8Array', () => {
    const resp = heatmap();
    const data = decodeHeatmap(resp);
    expect(data.hours).toBe(HEATMAP_HOURS);
    expect(data.cellCount).toBe(resp.cells.length);
    expect(data.levels).toBeInstanceOf(Uint8Array);
    expect(data.levels.length).toBe(resp.cells.length * 49);
    const first = resp.cells[0]!;
    expect(data.levels[10]).toBe(Number(first.levels[10]));
    expect(data.lats[0]).toBe(first.lat);
    expect(data.lons[0]).toBe(first.lon);
  });

  it('keeps 9 as unknown and treats malformed characters as unknown, never as Low', () => {
    const resp = heatmap();
    resp.cells = [{ lat: 40, lon: -100, levels: '09x' }];
    const data = decodeHeatmap(resp);
    expect(Array.from(data.levels.slice(0, 4))).toEqual([0, 9, 9, 9]);
  });

  it('reads the unknown-cell fixture', () => {
    const data = decodeHeatmap(heatmapWithUnknown());
    const counts = countLevelsAtHour(data, 0);
    expect(counts.unknown).toBeGreaterThan(0);
    expect(
      counts.low + counts.moderate + counts.high + counts.severe + counts.no_travel + counts.unknown,
    ).toBe(data.cellCount);
  });
});

describe('heatmap weights', () => {
  it('maps level codes to the PLAN §6 weights', () => {
    expect([0, 1, 2, 3, 4, 9].map(heatWeightForCode)).toEqual([0.1, 0.3, 0.5, 0.75, 1, 0]);
  });

  it('builds a per-hour match expression whose fallback (Unknown) is weight 0', () => {
    const expr = weightExpression(7) as unknown[];
    expect(expr[0]).toBe('match');
    expect(expr[1]).toEqual(['get', 'h7']);
    expect(expr.at(-1)).toBe(0);
    expect(expr).toContain(0.75);
  });

  it('draws the hollow Unknown dot only where the hour is 9', () => {
    expect(unknownOpacityExpression(3)).toEqual(['case', ['==', ['get', 'h3'], 9], 1, 0]);
  });

  it('exposes every hour as a feature property so scrubbing never re-requests data', () => {
    const data = decodeHeatmap(heatmap());
    const fc = toFeatureCollection(data);
    expect(fc.features).toHaveLength(data.cellCount);
    const props = fc.features[0]!.properties;
    expect(Object.keys(props)).toHaveLength(49);
    expect(props[hourProp(0)]).toBe(data.levels[0]);
    expect(props[hourProp(48)]).toBe(data.levels[48]);
  });
});

describe('time helpers', () => {
  it('converts a checkpoint ETA to a slider hour only when it is within 0–48 h', () => {
    const dep = '2026-11-02T12:00:00Z';
    expect(etaHourOffset(dep, '2026-11-02T12:00:00Z')).toBe(0);
    expect(etaHourOffset(dep, '2026-11-02T15:32:09Z')).toBe(4);
    expect(etaHourOffset(dep, '2026-11-04T12:00:00Z')).toBe(48);
    expect(etaHourOffset(dep, '2026-11-04T13:00:00Z')).toBeNull();
    expect(etaHourOffset(dep, '2026-11-02T11:00:00Z')).toBeNull();
    expect(etaHourOffset(dep, 'garbage')).toBeNull();
  });

  it('reads "now" in a given zone', () => {
    const now = new Date('2026-11-02T12:00:00Z');
    expect(nowInZone('America/Chicago', now)).toBe('2026-11-02T06:00');
    expect(nowInZone('Asia/Tokyo', now)).toBe('2026-11-02T21:00');
  });

  it('builds the departure window now − 15 min … now + 7 days', () => {
    const w = departureWindow('America/Chicago', new Date('2026-11-02T12:00:00Z'));
    expect(w).toEqual({ min: '2026-11-02T05:45', max: '2026-11-09T06:00' });
  });

  it('defaults the departure to the next full hour', () => {
    expect(nextFullHour('2026-11-02T06:00')).toBe('2026-11-02T07:00');
    expect(nextFullHour('2026-11-02T06:20')).toBe('2026-11-02T07:00');
  });
});
