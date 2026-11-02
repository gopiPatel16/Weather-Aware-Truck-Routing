import { describe, expect, it } from 'vitest';
import { CHICAGO, DENVER } from '../test/fixtures';
import { parseCargoWeight, validateTrip, type TripFormValues } from './validation';

// 2026-11-02 12:00 UTC = 06:00 CST in Chicago.
const NOW = new Date('2026-11-02T12:00:00Z');

const valid = (): TripFormValues => ({
  origin: CHICAGO,
  destination: DENVER,
  originText: CHICAGO.label,
  destinationText: DENVER.label,
  departure: '2026-11-02T08:00',
  cargoWeight: '42000',
  interval: 25,
});

describe('validateTrip', () => {
  it('accepts a complete trip', () => {
    expect(validateTrip(valid(), NOW)).toEqual({});
  });

  it('requires an origin and destination, and distinguishes "empty" from "typed but not picked"', () => {
    const empty = validateTrip(
      { ...valid(), origin: null, originText: '', destination: null, destinationText: '' },
      NOW,
    );
    expect(empty.origin).toMatch(/enter an origin/i);
    expect(empty.destination).toMatch(/enter a destination/i);
    const typed = validateTrip({ ...valid(), origin: null, originText: 'Chic' }, NOW);
    expect(typed.origin).toMatch(/pick an origin from the suggestions/i);
  });

  it('rejects an origin and destination closer than 5 miles', () => {
    const near = { ...CHICAGO, label: 'Chicago Loop', lat: CHICAGO.lat + 0.01 };
    expect(validateTrip({ ...valid(), destination: near }, NOW).destination).toMatch(/less than 5 miles/i);
  });

  it('checks the departure window in the ORIGIN zone, not the browser zone', () => {
    // 05:50 Chicago time is 10 min before "now" (06:00 CST): inside the 15-minute grace.
    expect(validateTrip({ ...valid(), departure: '2026-11-02T05:50' }, NOW).departure).toBeUndefined();
    // 05:44 is 16 minutes ago: rejected.
    expect(validateTrip({ ...valid(), departure: '2026-11-02T05:44' }, NOW).departure).toMatch(
      /in the past/i,
    );
    // Seven days ahead is the limit.
    expect(validateTrip({ ...valid(), departure: '2026-11-09T06:00' }, NOW).departure).toBeUndefined();
    expect(validateTrip({ ...valid(), departure: '2026-11-09T06:01' }, NOW).departure).toMatch(/7 days/);
  });

  it('requires a departure', () => {
    expect(validateTrip({ ...valid(), departure: '' }, NOW).departure).toMatch(/choose a departure/i);
  });

  it('validates cargo weight as pounds in (0, 150 000]', () => {
    const w = (cargoWeight: string) => validateTrip({ ...valid(), cargoWeight }, NOW).cargoWeight;
    expect(w('')).toMatch(/enter the cargo weight/i);
    expect(w('abc')).toMatch(/number of pounds/i);
    expect(w('0')).toMatch(/greater than 0/i);
    expect(w('-5')).toMatch(/number of pounds/i);
    expect(w('150001')).toMatch(/150,000 lb or less/);
    expect(w('150000')).toBeUndefined();
    expect(w('30,001')).toBeUndefined();
    expect(w('1')).toBeUndefined();
  });

  it('only allows the 10 / 25 / 50 mile intervals', () => {
    expect(validateTrip({ ...valid(), interval: 15 as never }, NOW).interval).toMatch(/10, 25 or 50/);
  });
});

describe('parseCargoWeight', () => {
  it('accepts thousands separators and rejects junk', () => {
    expect(parseCargoWeight('42,000')).toBe(42000);
    expect(parseCargoWeight(' 42 000 ')).toBe(42000);
    expect(parseCargoWeight('4.2e4')).toBeNaN();
    expect(parseCargoWeight('')).toBeNaN();
  });
});
