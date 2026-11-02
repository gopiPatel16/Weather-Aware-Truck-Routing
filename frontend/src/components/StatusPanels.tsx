import { useEffect, useState } from 'react';
import type { ApiError } from '../api/errors';
import type { RetryState } from '../state/usePlanner';

export const LOADING_STEPS = [
  'Finding truck routes',
  'Fetching weather forecast',
  'Scoring risk along each route',
] as const;

/** Elapsed-time driven: the backend answers in one response, so the steps are indicative of what it is doing. */
function useElapsedStep(): number {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t1 = setTimeout(() => setStep(1), 2500);
    const t2 = setTimeout(() => setStep(2), 5500);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);
  return step;
}

function useCountdown(retry: RetryState | null): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!retry) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [retry]);
  if (!retry) return null;
  return Math.max(0, Math.ceil((retry.startedAt + retry.info.delayMs - now) / 1000));
}

interface LoadingProps {
  retry: RetryState | null;
  onCancel: () => void;
  onRetryNow: () => void;
}

export function LoadingPanel({ retry, onCancel, onRetryNow }: LoadingProps) {
  const step = useElapsedStep();
  const seconds = useCountdown(retry);
  return (
    <section aria-label="Planning progress" className="rounded-xl border border-line bg-white p-3">
      {retry ? (
        <div
          role="status"
          className="mb-3 rounded-lg border border-amber-700 bg-amber-50 p-2 text-sm text-amber-950"
        >
          <strong>The server is starting up or busy.</strong> Retrying in {seconds} s (attempt{' '}
          {retry.info.attempt} of {retry.info.of})…
          <div className="mt-2">
            <button
              type="button"
              onClick={onRetryNow}
              className="rounded-md border border-amber-800 bg-white px-2.5 py-1 text-xs font-semibold hover:bg-amber-100"
            >
              Retry now
            </button>
          </div>
        </div>
      ) : null}
      {retry ? null : (
        <ol className="space-y-1.5 text-sm" aria-live="polite">
          {LOADING_STEPS.map((label, i) => (
            <li key={label} className={`flex items-center gap-2 ${i > step ? 'text-muted' : 'font-medium'}`}>
              <span aria-hidden="true" className="inline-block w-4 text-center">
                {i < step ? '✓' : i === step ? <span className="inline-block animate-spin">◌</span> : '○'}
              </span>
              {label}
              {i === step ? '…' : ''}
              <span className="sr-only">
                {i < step ? ' (done)' : i === step ? ' (in progress)' : ' (waiting)'}
              </span>
            </li>
          ))}
        </ol>
      )}
      <button
        type="button"
        onClick={onCancel}
        className="mt-3 rounded-md border border-line px-3 py-1 text-xs font-medium hover:bg-slate-100"
      >
        Cancel
      </button>
    </section>
  );
}

const TITLES: Record<string, string> = {
  validation_error: 'Check the trip details',
  invalid_departure_time: 'That departure time is not valid',
  no_route: 'No truck route found',
  trip_too_long: 'This trip is too long',
  rate_limited: 'Too many requests',
  routing_unavailable: 'Routing service unavailable',
  weather_unavailable: 'Weather service unavailable',
  quota_exceeded: 'Service quota reached',
  network_error: 'Could not reach the server',
};

const waitText = (s: number): string => (s >= 120 ? `${Math.round(s / 60)} minutes` : `${s} seconds`);

export function ErrorPanel({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  const retryable = error.isTransient || error.code === 'rate_limited';
  return (
    <section role="alert" className="rounded-xl border-2 border-red-800 bg-red-50 p-3 text-sm text-red-950">
      <h2 className="text-base font-bold">{TITLES[error.code] ?? 'Something went wrong'}</h2>
      <p className="mt-1">{error.message}</p>
      {error.fields ? (
        <ul className="mt-1 list-disc pl-5">
          {Object.entries(error.fields).flatMap(([field, msgs]) =>
            msgs.map((m) => (
              <li key={`${field}-${m}`}>
                {field.replace(/_/g, ' ')}: {m}
              </li>
            )),
          )}
        </ul>
      ) : null}
      {error.retryAfterS ? <p className="mt-1">Try again in about {waitText(error.retryAfterS)}.</p> : null}
      {error.isTransient ? (
        <p className="mt-1">The server may be starting up. Automatic retries have been used up.</p>
      ) : null}
      {retryable ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded-md bg-red-800 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-900"
        >
          Retry
        </button>
      ) : null}
    </section>
  );
}
