import { describe, expect, it } from 'vitest';
import {
  HEAT_WEIGHTS,
  RISK_ORDER,
  RISK_STYLES,
  UNKNOWN_CODE,
  heatWeightForCode,
  levelFromCode,
} from './risk';

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number];
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
};

describe('risk colour mapping', () => {
  it('defines every level with a label, a glyph and a letter (never colour alone)', () => {
    for (const level of RISK_ORDER) {
      const s = RISK_STYLES[level];
      expect(s.label.length).toBeGreaterThan(0);
      expect(s.icon.length).toBeGreaterThan(0);
      expect(s.letter.length).toBe(1);
    }
    expect(new Set(RISK_ORDER.map((l) => RISK_STYLES[l].icon)).size).toBe(RISK_ORDER.length);
    expect(new Set(RISK_ORDER.map((l) => RISK_STYLES[l].color)).size).toBe(RISK_ORDER.length);
  });

  it('uses the plan labels', () => {
    expect(RISK_ORDER.map((l) => RISK_STYLES[l].label)).toEqual([
      'Low',
      'Moderate',
      'High',
      'Severe',
      'No Travel',
      'Unknown',
    ]);
  });

  it('keeps AA contrast (≥ 4.5) for badge text on its tint', () => {
    for (const level of RISK_ORDER) {
      const s = RISK_STYLES[level];
      expect(contrast(s.fg, s.bg), level).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('draws higher risk larger on the map', () => {
    const r = (['low', 'moderate', 'high', 'severe', 'no_travel'] as const).map((l) => RISK_STYLES[l].radius);
    expect([...r].sort((a, b) => a - b)).toEqual(r);
    expect(new Set(r).size).toBe(r.length);
  });
});

describe('heat weights and level codes', () => {
  it('maps codes 0–4 to levels and everything else to unknown', () => {
    expect([0, 1, 2, 3, 4].map(levelFromCode)).toEqual(['low', 'moderate', 'high', 'severe', 'no_travel']);
    expect(levelFromCode(UNKNOWN_CODE)).toBe('unknown');
    expect(levelFromCode(7)).toBe('unknown');
  });

  it('uses the weights from PLAN §6 and never gives Unknown a weight', () => {
    expect(HEAT_WEIGHTS).toEqual({
      low: 0.1,
      moderate: 0.3,
      high: 0.5,
      severe: 0.75,
      no_travel: 1,
      unknown: 0,
    });
    expect([0, 1, 2, 3, 4, 9].map(heatWeightForCode)).toEqual([0.1, 0.3, 0.5, 0.75, 1, 0]);
  });
});
