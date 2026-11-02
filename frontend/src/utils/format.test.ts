import { describe, expect, it } from 'vitest';
import {
  formatDuration,
  formatDurationDelta,
  formatInHr,
  formatInZone,
  formatMiles,
  formatMph,
  formatTimeInZone,
  zoneAbbreviation,
} from './format';

describe('number and duration formatting', () => {
  it('formats durations in hours and minutes', () => {
    expect(formatDuration(60_120)).toBe('16 h 42 min');
    expect(formatDuration(7200)).toBe('2 h');
    expect(formatDuration(2700)).toBe('45 min');
    expect(formatDuration(-5)).toBe('0 min');
  });

  it('formats signed deltas', () => {
    expect(formatDurationDelta(2580)).toBe('+43 min');
    expect(formatDurationDelta(-3900)).toBe('−1 h 5 min');
  });

  it('formats values with their units and a dash for missing data', () => {
    expect(formatMiles(1003.2)).toBe('1,003 mi');
    expect(formatMph(41.24)).toBe('41.2 mph');
    expect(formatInHr(0.1)).toBe('0.10 in/hr');
    expect(formatInHr(null)).toBe('—');
    expect(formatMph(null)).toBe('—');
  });
});

describe('time-zone formatting', () => {
  it('formats the same instant in each zone with its own abbreviation', () => {
    const iso = '2026-11-02T22:10:00Z';
    expect(formatInZone(iso, 'America/Chicago')).toBe('Mon, Nov 2, 4:10 PM CST');
    expect(formatInZone(iso, 'America/Denver')).toBe('Mon, Nov 2, 3:10 PM MST');
    expect(formatInZone(iso, 'America/Los_Angeles')).toBe('Mon, Nov 2, 2:10 PM PST');
  });

  it('shows daylight abbreviations and handles the fall-back overlap', () => {
    // 2026-11-01 01:30 America/Chicago happens twice: first as CDT (06:30Z), then as CST (07:30Z).
    expect(formatTimeInZone('2026-11-01T06:30:00Z', 'America/Chicago')).toBe('1:30 AM CDT');
    expect(formatTimeInZone('2026-11-01T07:30:00Z', 'America/Chicago')).toBe('1:30 AM CST');
    expect(zoneAbbreviation('2026-07-01T12:00:00Z', 'America/Chicago')).toBe('CDT');
  });

  it('never depends on the browser zone', () => {
    // 12:00 UTC is 21:00 in Tokyo regardless of where the test machine is.
    expect(formatInZone('2026-11-02T12:00:00Z', 'Asia/Tokyo', { date: false, zone: false })).toBe('9:00 PM');
  });

  it('can drop the date and the abbreviation', () => {
    expect(formatInZone('2026-11-02T22:10:00Z', 'America/Chicago', { date: false, zone: false })).toBe(
      '4:10 PM',
    );
  });

  it('falls back gracefully for an unknown zone id and invalid dates', () => {
    expect(zoneAbbreviation('2026-11-02T12:00:00Z', 'Not/AZone')).toBe('Not/AZone');
    expect(formatInZone('not a date', 'America/Chicago')).toBe('—');
    expect(() => formatInZone('2026-11-02T12:00:00Z', 'Not/AZone')).not.toThrow();
  });
});
