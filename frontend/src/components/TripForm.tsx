import { useId, useMemo, useState, type FormEvent } from 'react';
import type { GeocodeResult, IntervalMiles, PlanRequest } from '../api/types';
import { zoneAbbreviation } from '../utils/format';
import { LOAD_THRESHOLD_HELP } from '../utils/rules';
import { departureWindow, naiveToMs, nextFullHour, nowInZone } from '../utils/time';
import {
  INTERVAL_OPTIONS,
  parseCargoWeight,
  validateTrip,
  type TripErrors,
  type TripField,
  type TripFormValues,
} from '../utils/validation';
import { PlaceInput } from './PlaceInput';

export interface TripFormInitial {
  origin?: GeocodeResult;
  destination?: GeocodeResult;
  cargoWeight?: string;
  interval?: IntervalMiles;
}

interface Props {
  busy: boolean;
  initial?: TripFormInitial;
  onSubmit: (request: PlanRequest) => void;
}

const defaultDeparture = (tz: string | null): string => nextFullHour(nowInZone(tz));

export function TripForm({ busy, initial, onSubmit }: Props) {
  const uid = useId();
  const [values, setValues] = useState<TripFormValues>(() => ({
    origin: initial?.origin ?? null,
    destination: initial?.destination ?? null,
    originText: initial?.origin?.label ?? '',
    destinationText: initial?.destination?.label ?? '',
    departure: defaultDeparture(initial?.origin?.timezone ?? null),
    cargoWeight: initial?.cargoWeight ?? '',
    interval: initial?.interval ?? 25,
  }));
  const [departureEdited, setDepartureEdited] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const errors: TripErrors = useMemo(() => validateTrip(values), [values]);
  const shown = (field: TripField): string | undefined => (submitted ? errors[field] : undefined);

  const tz = values.origin?.timezone ?? null;
  const depWindow = useMemo(() => departureWindow(tz), [tz]);
  const zoneLabel = useMemo(() => {
    if (!tz) return null;
    const probe = Number.isNaN(naiveToMs(values.departure))
      ? new Date()
      : new Date(naiveToMs(values.departure));
    return `${tz.replace('_', ' ')} · ${zoneAbbreviation(probe, tz)}`;
  }, [tz, values.departure]);

  const patch = (next: Partial<TripFormValues>) => {
    setValues((v) => ({ ...v, ...next }));
  };

  const selectOrigin = (place: GeocodeResult) => {
    // Until the user types their own departure, keep the default aligned with the origin's wall clock.
    patch({
      origin: place,
      originText: place.label,
      ...(departureEdited ? {} : { departure: defaultDeparture(place.timezone) }),
    });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(errors).length > 0 || !values.origin || !values.destination) return;
    onSubmit({
      origin: { label: values.origin.label, lat: values.origin.lat, lon: values.origin.lon },
      destination: {
        label: values.destination.label,
        lat: values.destination.lat,
        lon: values.destination.lon,
      },
      // Naive local time: the backend reads it in the ORIGIN's zone, never the browser's.
      departure_local: values.departure.slice(0, 16),
      cargo_weight_lb: parseCargoWeight(values.cargoWeight),
      interval_miles: values.interval,
    });
  };

  const departureHelpId = `${uid}-dep-help`;
  const cargoHelpId = `${uid}-cargo-help`;
  const errorList = Object.entries(errors) as [TripField, string][];

  return (
    <form onSubmit={submit} noValidate aria-label="Trip details" className="space-y-3">
      <PlaceInput
        label="Origin"
        text={values.originText}
        selected={values.origin}
        error={shown('origin')}
        placeholder="e.g. Chicago, IL"
        onTextChange={(t) => patch({ originText: t, origin: null })}
        onSelect={selectOrigin}
      />
      <PlaceInput
        label="Destination"
        text={values.destinationText}
        selected={values.destination}
        error={shown('destination')}
        placeholder="e.g. Denver, CO"
        onTextChange={(t) => patch({ destinationText: t, destination: null })}
        onSelect={(p) => patch({ destination: p, destinationText: p.label })}
      />

      <div>
        <label htmlFor={`${uid}-dep`} className="mb-1 block text-sm font-semibold">
          Departure (local time at origin)
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input
            id={`${uid}-dep`}
            type="datetime-local"
            value={values.departure}
            min={depWindow.min}
            max={depWindow.max}
            aria-invalid={shown('departure') ? true : undefined}
            aria-describedby={departureHelpId}
            onChange={(e) => {
              setDepartureEdited(true);
              patch({ departure: e.target.value });
            }}
            className={`rounded-lg border bg-white px-3 py-2 text-sm ${shown('departure') ? 'border-red-700' : 'border-slate-400'}`}
          />
          <span
            data-testid="origin-zone"
            className={`rounded-md border px-2 py-1 text-xs font-semibold ${
              zoneLabel ? 'border-sky-700 bg-sky-50 text-sky-950' : 'border-line bg-slate-50 text-muted'
            }`}
          >
            {zoneLabel ?? 'Time zone: choose an origin'}
          </span>
        </div>
        <p id={departureHelpId} className="mt-1 text-xs text-muted">
          Read in the origin&apos;s time zone, not your browser&apos;s. Up to 7 days ahead.
        </p>
        {shown('departure') ? (
          <p className="mt-1 text-xs font-medium text-red-800">{shown('departure')}</p>
        ) : null}
      </div>

      <div>
        <label htmlFor={`${uid}-cargo`} className="mb-1 block text-sm font-semibold">
          Cargo/load weight (lb)
        </label>
        <input
          id={`${uid}-cargo`}
          type="text"
          inputMode="numeric"
          value={values.cargoWeight}
          placeholder="e.g. 42000"
          aria-invalid={shown('cargoWeight') ? true : undefined}
          aria-describedby={cargoHelpId}
          onChange={(e) => patch({ cargoWeight: e.target.value })}
          className={`w-44 rounded-lg border bg-white px-3 py-2 text-sm tabular-nums ${shown('cargoWeight') ? 'border-red-700' : 'border-slate-400'}`}
        />
        <p id={cargoHelpId} className="mt-1 text-xs text-muted">
          {LOAD_THRESHOLD_HELP}
        </p>
        {shown('cargoWeight') ? (
          <p className="mt-1 text-xs font-medium text-red-800">{shown('cargoWeight')}</p>
        ) : null}
      </div>

      <fieldset>
        <legend className="mb-1 text-sm font-semibold">Check weather every</legend>
        <div className="inline-flex overflow-hidden rounded-lg border border-slate-400" role="radiogroup">
          {INTERVAL_OPTIONS.map((mi) => (
            <label
              key={mi}
              className={`cursor-pointer px-4 py-2 text-sm font-medium has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-blue-700 ${
                values.interval === mi ? 'bg-brand text-white' : 'bg-white hover:bg-slate-100'
              }`}
            >
              <input
                type="radio"
                name={`${uid}-interval`}
                value={mi}
                checked={values.interval === mi}
                onChange={() => patch({ interval: mi })}
                className="sr-only"
              />
              {mi} mi
            </label>
          ))}
        </div>
      </fieldset>

      {submitted && errorList.length > 0 ? (
        <div
          role="alert"
          className="rounded-lg border border-red-800 bg-red-50 px-3 py-2 text-sm text-red-950"
        >
          Please fix {errorList.length} {errorList.length === 1 ? 'field' : 'fields'} before planning.
        </div>
      ) : null}

      <button
        type="submit"
        disabled={busy}
        className="w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-dark disabled:cursor-wait disabled:opacity-70"
      >
        {busy ? 'Planning…' : 'Find safest route'}
      </button>
    </form>
  );
}
