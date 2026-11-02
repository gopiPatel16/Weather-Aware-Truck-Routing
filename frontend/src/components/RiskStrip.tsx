import type { Route } from '../api/types';
import { formatMiles } from '../utils/format';
import { RISK_ORDER, RISK_STYLES } from '../utils/risk';

const HATCH = {
  unknown: 'repeating-linear-gradient(45deg, #c3c9d0 0 4px, #eceff2 4px 8px)',
  no_travel: 'repeating-linear-gradient(45deg, #2b0f4d 0 4px, #6b4a99 4px 8px)',
} as const;

/** Proportional strip of risk along the route. Unknown and No Travel use patterns, not just colour. */
export function RiskStrip({ route }: { route: Route }) {
  const total = route.distance_mi || 1;
  const mi = route.summary.miles_by_level;
  const description = RISK_ORDER.filter((l) => mi[l] > 0)
    .map((l) => `${formatMiles(mi[l])} ${RISK_STYLES[l].label}`)
    .join(', ');
  return (
    <div role="img" aria-label={`Risk along ${route.name}: ${description}`} className="mt-2">
      <div className="flex h-3 overflow-hidden rounded-full border border-slate-300 bg-slate-100">
        {route.segments.map((s, i) => (
          <span
            key={i}
            title={`${RISK_STYLES[s.level].label}: miles ${Math.round(s.from_mi)}–${Math.round(s.to_mi)}`}
            style={{
              width: `${((s.to_mi - s.from_mi) / total) * 100}%`,
              background:
                s.level === 'unknown' || s.level === 'no_travel'
                  ? HATCH[s.level]
                  : RISK_STYLES[s.level].color,
            }}
          />
        ))}
      </div>
    </div>
  );
}
