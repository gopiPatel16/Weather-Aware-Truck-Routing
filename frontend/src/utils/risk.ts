import type { KnownRiskLevel, RiskLevel } from '../api/types';

export interface RiskStyle {
  label: string;
  /** Short letter drawn inside map markers (a non-colour cue). */
  letter: string;
  /** Glyph used in badges (a non-colour cue). */
  icon: string;
  /** Strong colour for map markers, lines and swatches. */
  color: string;
  /** Light tint for badge backgrounds. */
  bg: string;
  /** Dark text colour that keeps AA contrast on `bg`. */
  fg: string;
  /** Marker radius in px; higher risk is drawn larger as a further non-colour cue. */
  radius: number;
}

export const RISK_ORDER: readonly RiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel', 'unknown'];

export const RISK_STYLES: Record<RiskLevel, RiskStyle> = {
  low: { label: 'Low', letter: 'L', icon: '●', color: '#2f9e5f', bg: '#dff3e7', fg: '#10492a', radius: 7 },
  moderate: {
    label: 'Moderate',
    letter: 'M',
    icon: '◆',
    color: '#e5b100',
    bg: '#fcefb8',
    fg: '#523d00',
    radius: 8,
  },
  high: { label: 'High', letter: 'H', icon: '▲', color: '#f08a1c', bg: '#fddcb8', fg: '#703400', radius: 9 },
  severe: {
    label: 'Severe',
    letter: 'S',
    icon: '■',
    color: '#d92d20',
    bg: '#fbd3cf',
    fg: '#7f1710',
    radius: 10,
  },
  no_travel: {
    label: 'No Travel',
    letter: 'X',
    icon: '⊘',
    color: '#2b0f4d',
    bg: '#e2d6f0',
    fg: '#2b0f4d',
    radius: 11,
  },
  unknown: {
    label: 'Unknown',
    letter: '?',
    icon: '?',
    color: '#7c8591',
    bg: '#e8ebee',
    fg: '#363e47',
    radius: 7,
  },
};

export const riskLabel = (level: RiskLevel): string => RISK_STYLES[level].label;

/** Heat-layer weight per level (PLAN §6). Unknown contributes nothing — it is drawn as a hollow dot instead. */
export const HEAT_WEIGHTS: Record<RiskLevel, number> = {
  low: 0.1,
  moderate: 0.3,
  high: 0.5,
  severe: 0.75,
  no_travel: 1,
  unknown: 0,
};

/** Numeric code used in heatmap `levels` strings: 0–4 known, 9 unknown. */
export const UNKNOWN_CODE = 9;

const KNOWN_BY_CODE: readonly KnownRiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel'];

export function levelFromCode(code: number): RiskLevel {
  return KNOWN_BY_CODE[code] ?? 'unknown';
}

export const heatWeightForCode = (code: number): number => HEAT_WEIGHTS[levelFromCode(code)];

export const REASON_TEXT = {
  no_travel: 'Has No Travel conditions',
  incomplete_weather: 'Weather forecast incomplete',
} as const;

export const ROUTE_COLORS = ['#1d4ed8', '#0e7490', '#a21caf', '#4d7c0f'] as const;
export const routeColor = (index: number): string => ROUTE_COLORS[index % ROUTE_COLORS.length] ?? '#1d4ed8';
