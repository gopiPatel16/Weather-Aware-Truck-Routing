import type { Checkpoint } from '../api/types';
import { formatInZone, formatTimeInZone } from './format';

/** Hour-of-day range with zone, e.g. "3:00 PM – 4:00 PM CST". */
function intervalLabel(start: string, end: string, tz: string): string {
  const zoned = formatTimeInZone(end, tz);
  const startOnly = formatInZone(start, tz, { date: false, zone: false });
  return `${startOnly} – ${zoned}`;
}

/**
 * Plain-language description of the forecast hours behind a checkpoint's weather values
 * (PLAN §5.4): precipitation intervals, wind stamps, and whether the adjacent interval was also checked.
 */
export function forecastBasisText(cp: Checkpoint): string[] {
  const basis = cp.weather?.basis;
  if (!basis) return ['No forecast data for this checkpoint'];
  const lines: string[] = [];
  const [covering, ...adjacent] = basis.precip_intervals;
  if (covering) lines.push(`Precipitation: ${intervalLabel(covering[0], covering[1], cp.tz)}`);
  for (const a of adjacent)
    lines.push(`Also checked: ${intervalLabel(a[0], a[1], cp.tz)} (ETA near the hour edge)`);
  if (basis.wind_stamps.length === 2) {
    const [a, b] = basis.wind_stamps as [string, string];
    lines.push(`Wind: ${formatTimeInZone(a, cp.tz)} → ${formatTimeInZone(b, cp.tz)} (interpolated)`);
  } else if (basis.wind_stamps.length === 1) {
    lines.push(`Wind: ${formatTimeInZone(basis.wind_stamps[0] as string, cp.tz)}`);
  }
  return lines;
}

/** One-line version for table cells. */
export function forecastBasisShort(cp: Checkpoint): string {
  const basis = cp.weather?.basis;
  if (!basis) return '—';
  const covering = basis.precip_intervals[0];
  const base = covering ? intervalLabel(covering[0], covering[1], cp.tz) : '—';
  return basis.adjacent_interval_used ? `${base} + adjacent` : base;
}
