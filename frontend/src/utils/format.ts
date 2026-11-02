const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const formatMiles = (mi: number): string => `${nf0.format(mi)} mi`;
export const formatMilesPrecise = (mi: number): string => `${nf1.format(mi)} mi`;
export const formatLb = (lb: number): string => `${nf0.format(lb)} lb`;
export const formatPercent = (pct: number): string => `${nf1.format(pct)}%`;

/** 60 120 s → "16 h 42 min"; under an hour → "45 min". */
export function formatDuration(seconds: number): string {
  const totalMin = Math.max(0, Math.round(seconds / 60));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

/** Signed difference such as "+43 min" or "−1 h 05 min". */
export function formatDurationDelta(seconds: number): string {
  const sign = seconds < 0 ? '−' : '+';
  return `${sign}${formatDuration(Math.abs(seconds))}`;
}

export const formatMph = (v: number | null): string => (v == null ? '—' : `${nf1.format(v)} mph`);
export const formatInHr = (v: number | null): string => (v == null ? '—' : `${nf2.format(v)} in/hr`);
export const formatTempF = (v: number | null): string => (v == null ? '—' : `${nf0.format(v)} °F`);
export const formatAvgRisk = (v: number | null): string => (v == null ? '—' : nf2.format(v));

export interface ZonedFormatOptions {
  /** Include the weekday and date (default true). */
  date?: boolean;
  /** Include the zone abbreviation, e.g. "CST" (default true). */
  zone?: boolean;
}

function safeZone(tz: string): string | undefined {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz });
    return tz;
  } catch {
    return undefined;
  }
}

/** Zone abbreviation for an instant in an IANA zone, e.g. "CDT". Falls back to the zone id. */
export function zoneAbbreviation(iso: string | Date, tz: string): string {
  const zone = safeZone(tz);
  if (!zone) return tz;
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'short' }).formatToParts(
    typeof iso === 'string' ? new Date(iso) : iso,
  );
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? tz;
}

/** Formats an instant in the given IANA zone, e.g. "Mon, Nov 2, 4:10 PM CST". Never uses the browser's zone. */
export function formatInZone(iso: string | Date, tz: string, opts: ZonedFormatOptions = {}): string {
  const { date = true, zone = true } = opts;
  const timeZone = safeZone(tz);
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return '—';
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone,
    ...(date ? { weekday: 'short', month: 'short', day: 'numeric' } : {}),
    hour: 'numeric',
    minute: '2-digit',
    ...(zone ? { timeZoneName: 'short' } : {}),
  });
  return fmt.format(d);
}

/** Time only, with abbreviation: "4:10 PM CST". */
export const formatTimeInZone = (iso: string | Date, tz: string): string =>
  formatInZone(iso, tz, { date: false });

/** Offset of a slider hour from departure: "+6 h". */
export const formatHourOffset = (h: number): string => (h === 0 ? 'Departure' : `+${h} h`);

export const lbToThousands = (lb: number): string => `${nf0.format(lb / 1000)}k`;
