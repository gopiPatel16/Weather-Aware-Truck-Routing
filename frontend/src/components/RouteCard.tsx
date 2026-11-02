import { memo } from 'react';
import type { Route } from '../api/types';
import {
  formatAvgRisk,
  formatDuration,
  formatDurationDelta,
  formatInZone,
  formatMiles,
  formatMilesPrecise,
  formatPercent,
} from '../utils/format';
import { RiskStrip } from './RiskStrip';
import { routeColor } from '../utils/risk';

interface Props {
  route: Route;
  index: number;
  selected: boolean;
  recommended: boolean;
  /** Seconds slower than the fastest returned route (0 for the fastest). */
  slowerBySeconds: number;
  onSelect: (id: string) => void;
}

export function eligibilityText(route: Route): string[] {
  return route.eligibility.reasons.map((r) =>
    r === 'no_travel'
      ? `No Travel conditions on ${formatMilesPrecise(route.summary.no_travel_mi)}`
      : `Forecast covers only ${formatPercent(route.summary.coverage_pct)} of the route`,
  );
}

function Stat({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className={`text-sm font-semibold tabular-nums ${warn ? 'text-red-800' : 'text-ink'}`}>{value}</dd>
    </div>
  );
}

function RouteCardBase({ route, index, selected, recommended, slowerBySeconds, onSelect }: Props) {
  const { summary, eligibility } = route;
  const estimated = route.eta_method === 'estimated_uniform_speed';
  const reasons = eligibilityText(route);
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(route.id)}
        className={`block w-full rounded-xl border-2 bg-white p-3 text-left shadow-sm transition-colors hover:bg-slate-50 ${
          selected ? 'border-brand ring-2 ring-brand/20' : 'border-line'
        }`}
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            aria-hidden="true"
            className="inline-block size-3 rounded-full"
            style={{ background: routeColor(index) }}
          />
          <span className="text-base font-bold">{route.name}</span>
          {route.via ? <span className="text-sm text-muted">via {route.via}</span> : null}
          <span className="ml-auto flex flex-wrap items-center gap-1">
            {recommended ? (
              <span className="rounded-md bg-emerald-700 px-1.5 py-0.5 text-xs font-bold text-white">
                ★ Recommended
              </span>
            ) : null}
            {eligibility.eligible ? (
              <span className="rounded-md border border-emerald-700 bg-emerald-50 px-1.5 py-0.5 text-xs font-semibold text-emerald-900">
                ✓ Eligible
              </span>
            ) : (
              <span className="rounded-md border border-red-800 bg-red-50 px-1.5 py-0.5 text-xs font-semibold text-red-900">
                ⊘ Not eligible
              </span>
            )}
          </span>
        </span>

        {reasons.length > 0 ? (
          <span className="mt-1 block text-xs font-medium text-red-900">{reasons.join(' · ')}</span>
        ) : null}

        <dl className="mt-2 grid grid-cols-3 gap-x-3 gap-y-2">
          <Stat label="Distance" value={formatMiles(route.distance_mi)} />
          <Stat
            label="Duration"
            value={`${formatDuration(route.duration_s)}${slowerBySeconds > 60 ? ` (${formatDurationDelta(slowerBySeconds)})` : ''}`}
          />
          <Stat
            label="Weather coverage"
            value={formatPercent(summary.coverage_pct)}
            warn={summary.coverage_pct < 100}
          />
          <Stat label="Severe" value={formatMilesPrecise(summary.severe_mi)} warn={summary.severe_mi > 0} />
          <Stat label="High" value={formatMilesPrecise(summary.high_mi)} />
          <Stat label="Avg risk" value={formatAvgRisk(summary.avg_risk)} />
          {summary.no_travel_mi > 0 ? (
            <Stat label="No Travel" value={formatMilesPrecise(summary.no_travel_mi)} warn />
          ) : null}
          {summary.miles_by_level.unknown > 0 ? (
            <Stat label="Unknown" value={formatMilesPrecise(summary.miles_by_level.unknown)} warn />
          ) : null}
        </dl>

        <span className="mt-2 block text-sm">
          <span className="font-medium">Arrives </span>
          {formatInZone(route.arrival_utc, route.arrival_tz)}
        </span>
        <span className={`block text-xs ${estimated ? 'font-semibold text-amber-900' : 'text-muted'}`}>
          {estimated ? '⚠ ETAs estimated from average speed' : 'ETAs from route travel times'}
        </span>

        <RiskStrip route={route} />
      </button>
    </li>
  );
}

export const RouteCard = memo(RouteCardBase);
