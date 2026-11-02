/** A naive local timestamp without offset: `YYYY-MM-DDTHH:MM`. */
export type NaiveLocal = string;

const MIN = 60_000;

/** "Now" as a naive wall-clock string in the given IANA zone. */
export function nowInZone(tz: string | null, now: Date = new Date()): NaiveLocal {
  const parts = new Intl.DateTimeFormat('en-CA', {
    ...(tz ? { timeZone: tz } : {}),
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

/** Wall-clock arithmetic on naive strings (treats them as UTC so DST never shifts the result). */
export function naiveToMs(value: NaiveLocal): number {
  return Date.parse(`${value.slice(0, 16)}:00Z`);
}

export function addMinutesNaive(value: NaiveLocal, minutes: number): NaiveLocal {
  return new Date(naiveToMs(value) + minutes * MIN).toISOString().slice(0, 16);
}

/** Round up to the next whole hour (used for the default departure). */
export function nextFullHour(value: NaiveLocal): NaiveLocal {
  const ms = naiveToMs(value);
  const hour = 60 * MIN;
  return new Date(Math.ceil((ms + 1) / hour) * hour).toISOString().slice(0, 16);
}

export interface DepartureWindow {
  min: NaiveLocal;
  max: NaiveLocal;
}

/** PLAN D13: now − 15 min … now + 7 days, expressed in the origin zone's wall clock. */
export function departureWindow(tz: string | null, now: Date = new Date()): DepartureWindow {
  const current = nowInZone(tz, now);
  return { min: addMinutesNaive(current, -15), max: addMinutesNaive(current, 7 * 24 * 60) };
}

/** Whole-hour offset of an ETA from departure, or null when outside the 0–48 h slider range. */
export function etaHourOffset(departureUtc: string, etaUtc: string, maxHour = 48): number | null {
  const diff = (Date.parse(etaUtc) - Date.parse(departureUtc)) / (60 * MIN);
  if (!Number.isFinite(diff)) return null;
  const h = Math.round(diff);
  return h >= 0 && h <= maxHour ? h : null;
}
