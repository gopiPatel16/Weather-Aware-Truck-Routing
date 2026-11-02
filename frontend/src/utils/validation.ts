import type { GeocodeResult, IntervalMiles } from '../api/types';
import { departureWindow, naiveToMs } from './time';

export const INTERVAL_OPTIONS: readonly IntervalMiles[] = [10, 25, 50];
export const MAX_CARGO_LB = 150_000;
/** Origin and destination closer than this are rejected (PLAN §5.8). */
export const MIN_TRIP_MILES = 5;

export interface TripFormValues {
  origin: GeocodeResult | null;
  destination: GeocodeResult | null;
  /** Text typed in the boxes — used to tell "nothing typed" from "typed but not picked". */
  originText: string;
  destinationText: string;
  departure: string;
  cargoWeight: string;
  interval: IntervalMiles;
}

export type TripField = 'origin' | 'destination' | 'departure' | 'cargoWeight' | 'interval';
export type TripErrors = Partial<Record<TripField, string>>;

const EARTH_RADIUS_MI = 3958.8;

export function haversineMiles(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h));
}

/** Accepts "42000", "42,000" and "42 000"; returns NaN for anything else. */
export function parseCargoWeight(raw: string): number {
  const cleaned = raw.trim().replace(/[,\s]/g, '');
  return /^\d+(\.\d+)?$/.test(cleaned) ? Number(cleaned) : NaN;
}

export function validateTrip(values: TripFormValues, now: Date = new Date()): TripErrors {
  const errors: TripErrors = {};

  if (!values.origin) {
    errors.origin = values.originText.trim()
      ? 'Pick an origin from the suggestions.'
      : 'Enter an origin (city or address).';
  }
  if (!values.destination) {
    errors.destination = values.destinationText.trim()
      ? 'Pick a destination from the suggestions.'
      : 'Enter a destination (city or address).';
  }
  if (
    values.origin &&
    values.destination &&
    haversineMiles(values.origin, values.destination) < MIN_TRIP_MILES
  ) {
    errors.destination = `Origin and destination are less than ${MIN_TRIP_MILES} miles apart.`;
  }

  if (!values.departure) {
    errors.departure = 'Choose a departure date and time.';
  } else if (Number.isNaN(naiveToMs(values.departure))) {
    errors.departure = 'Enter a valid departure date and time.';
  } else {
    const { min, max } = departureWindow(values.origin?.timezone ?? null, now);
    const t = naiveToMs(values.departure);
    if (t < naiveToMs(min)) errors.departure = 'Departure is in the past. Choose the current time or later.';
    else if (t > naiveToMs(max))
      errors.departure = 'Departure must be within the next 7 days (the forecast limit).';
  }

  const weight = parseCargoWeight(values.cargoWeight);
  if (!values.cargoWeight.trim()) errors.cargoWeight = 'Enter the cargo weight in pounds.';
  else if (!Number.isFinite(weight)) errors.cargoWeight = 'Cargo weight must be a number of pounds.';
  else if (weight <= 0) errors.cargoWeight = 'Cargo weight must be greater than 0 lb.';
  else if (weight > MAX_CARGO_LB) {
    errors.cargoWeight = `Cargo weight must be ${MAX_CARGO_LB.toLocaleString('en-US')} lb or less.`;
  }

  if (!INTERVAL_OPTIONS.includes(values.interval)) errors.interval = 'Choose 10, 25 or 50 miles.';

  return errors;
}
