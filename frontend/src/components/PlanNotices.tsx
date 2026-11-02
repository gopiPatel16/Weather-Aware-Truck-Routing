import type { PlanResponse } from '../api/types';

/** Alternatives message plus backend warnings and estimated-ETA / adjusted-interval notices. */
export function PlanNotices({ plan }: { plan: PlanResponse }) {
  const { alternatives, request, routes } = plan;
  const estimated = routes.some((r) => r.eta_method === 'estimated_uniform_speed');
  const fewer = alternatives.usable < alternatives.requested;
  // Estimated-ETA warnings are summarised once below, so drop the per-route duplicates.
  const warnings = request.warnings.filter((w) => !/estimated from average speed/i.test(w));
  return (
    <div className="space-y-2">
      <p
        data-testid="alternatives-message"
        data-limited={fewer}
        className={`rounded-lg border px-3 py-2 text-sm ${
          fewer ? 'border-sky-700 bg-sky-50 text-sky-950' : 'border-line bg-white text-muted'
        }`}
      >
        <span aria-hidden="true">{fewer ? 'ℹ ' : '✓ '}</span>
        {alternatives.message}
      </p>
      {estimated ? (
        <p className="rounded-lg border border-amber-700 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          <span aria-hidden="true">⚠ </span>
          Route timing data was unavailable, so ETAs are estimated from average speed.
        </p>
      ) : null}
      {request.interval_adjusted ? (
        <p className="rounded-lg border border-amber-700 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          <span aria-hidden="true">⚠ </span>
          The sampling interval was raised from {request.requested_interval_miles ?? '?'} to{' '}
          {request.interval_miles} mi to keep the route under the checkpoint limit.
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <ul className="space-y-1">
          {warnings.map((w) => (
            <li
              key={w}
              className="rounded-lg border border-amber-700 bg-amber-50 px-3 py-2 text-sm text-amber-950"
            >
              <span aria-hidden="true">⚠ </span>
              {w}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
