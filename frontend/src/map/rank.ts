import type { RiskLevel } from '../api/types';

const ORDER: Record<RiskLevel, number> = {
  unknown: 0,
  low: 1,
  moderate: 2,
  high: 3,
  severe: 4,
  no_travel: 5,
};

/** Draw order for overlapping markers: Unknown at the bottom, No Travel on top. Not a risk score. */
export const levelRankForSort = (level: RiskLevel): number => ORDER[level];
