import type { TripFormInitial } from '../src/components/TripForm';

/** Pre-filled trip for mock mode (Chicago → Denver, the route the fixtures describe). */
export const DEMO_TRIP: TripFormInitial = {
  origin: { label: 'Chicago, IL, USA', lat: 41.8781, lon: -87.6298, timezone: 'America/Chicago' },
  destination: { label: 'Denver, CO, USA', lat: 39.7392, lon: -104.9903, timezone: 'America/Denver' },
  cargoWeight: '42000',
  interval: 25,
};
