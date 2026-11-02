import { memo, useEffect, useMemo, useRef, useState } from 'react';
import type { Checkpoint, Route } from '../api/types';
import {
  formatInHr,
  formatInZone,
  formatMiles,
  formatMph,
  formatTempF,
  zoneAbbreviation,
} from '../utils/format';
import { forecastBasisText } from '../utils/forecast';
import { RISK_STYLES } from '../utils/risk';
import { RiskBadge } from './RiskBadge';

interface Props {
  route: Route;
  intervalMiles: number;
  selectedIndex: number | null;
  onSelect: (routeId: string, index: number) => void;
}

const MODERATE_UP = new Set(['moderate', 'high', 'severe', 'no_travel', 'unknown']);

function CheckpointRow({
  route,
  cp,
  selected,
  onSelect,
}: {
  route: Route;
  cp: Checkpoint;
  selected: boolean;
  onSelect: Props['onSelect'];
}) {
  const ref = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView?.({ block: 'nearest' });
  }, [selected]);
  const w = cp.weather;
  const atLeast =
    cp.risk.level === 'unknown' && cp.risk.at_least
      ? `at least ${RISK_STYLES[cp.risk.at_least].label}`
      : undefined;
  const wind =
    w?.gust_mph != null
      ? `${formatMph(w.wind_mph)} (gust ${formatMph(w.gust_mph)})`
      : formatMph(w?.wind_mph ?? null);
  return (
    <tr
      ref={ref}
      aria-current={selected ? 'true' : undefined}
      className={selected ? 'bg-sky-50' : 'odd:bg-white even:bg-slate-50/60'}
    >
      <th scope="row" className="whitespace-nowrap px-2 py-1.5 text-left font-semibold tabular-nums">
        <button
          type="button"
          onClick={() => onSelect(route.id, cp.i)}
          aria-label={`Show checkpoint at mile ${cp.mile} on the map`}
          className="rounded px-1 underline decoration-dotted underline-offset-2 hover:bg-sky-100"
        >
          {formatMiles(cp.mile)}
        </button>
      </th>
      <td className="whitespace-nowrap px-2 py-1.5">
        {formatInZone(cp.eta_utc, cp.tz)}
        <span className="block text-[11px] text-muted">{cp.tz.replace('_', ' ')}</span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">{wind}</td>
      <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">{formatInHr(w?.rain_in_hr ?? null)}</td>
      <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">{formatInHr(w?.snow_in_hr ?? null)}</td>
      <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">{formatTempF(w?.temp_f ?? null)}</td>
      <td className="px-2 py-1.5 text-xs text-muted">
        {forecastBasisText(cp).map((line) => (
          <span key={line} className="block whitespace-nowrap">
            {line}
          </span>
        ))}
      </td>
      <td className="px-2 py-1.5">
        <RiskBadge level={cp.risk.level} suffix={atLeast} />
        {cp.risk.drivers.length > 0 ? (
          <span className="mt-0.5 block text-[11px] leading-tight text-muted">
            {cp.risk.drivers.map((d) => d.text).join('; ')}
          </span>
        ) : null}
        {cp.risk.level === 'unknown' && cp.risk.missing.length > 0 ? (
          <span className="mt-0.5 block text-[11px] text-muted">Missing: {cp.risk.missing.join(', ')}</span>
        ) : null}
      </td>
    </tr>
  );
}

function CheckpointTableBase({ route, intervalMiles, selectedIndex, onSelect }: Props) {
  const [onlyElevated, setOnlyElevated] = useState(false);
  const rows = useMemo(
    () => (onlyElevated ? route.checkpoints.filter((c) => MODERATE_UP.has(c.risk.level)) : route.checkpoints),
    [onlyElevated, route.checkpoints],
  );
  const abbr = route.checkpoints[0]
    ? zoneAbbreviation(route.checkpoints[0].eta_utc, route.checkpoints[0].tz)
    : '';
  return (
    <section aria-labelledby="cp-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="cp-heading" className="text-sm font-bold">
          Checkpoints — {route.name} (every {intervalMiles} mi)
        </h3>
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={onlyElevated} onChange={(e) => setOnlyElevated(e.target.checked)} />
          Moderate or worse, and Unknown
        </label>
      </div>
      <p className="mb-1 text-xs text-muted">
        Times are in each checkpoint&apos;s own time zone{abbr ? ` (starts in ${abbr})` : ''}. Precipitation
        is an hourly total for the forecast hour shown.
      </p>
      <div className="max-h-[22rem] overflow-auto rounded-lg border border-line">
        <table className="w-full min-w-[46rem] border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-slate-100 text-left text-[11px] uppercase tracking-wide text-muted">
            <tr>
              <th scope="col" className="px-2 py-1.5">
                Mile
              </th>
              <th scope="col" className="px-2 py-1.5">
                ETA (local)
              </th>
              <th scope="col" className="px-2 py-1.5">
                Wind
              </th>
              <th scope="col" className="px-2 py-1.5">
                Rain
              </th>
              <th scope="col" className="px-2 py-1.5">
                Snow
              </th>
              <th scope="col" className="px-2 py-1.5">
                Temp
              </th>
              <th scope="col" className="px-2 py-1.5">
                Forecast hours used
              </th>
              <th scope="col" className="px-2 py-1.5">
                Risk
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((cp) => (
              <CheckpointRow
                key={cp.i}
                route={route}
                cp={cp}
                selected={cp.i === selectedIndex}
                onSelect={onSelect}
              />
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-2 py-3 text-center text-sm text-muted">
                  No Moderate or worse checkpoints on this route.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export const CheckpointTable = memo(CheckpointTableBase);
