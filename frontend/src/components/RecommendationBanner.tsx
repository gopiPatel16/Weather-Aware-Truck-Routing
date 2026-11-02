import type { PlanResponse } from '../api/types';
import { formatPercent } from '../utils/format';

export const NO_SAFE_ROUTE_HEADLINE = 'No safe route available';
export const INCONCLUSIVE_HEADLINE = 'A safe recommendation cannot be determined';

/** Banner for the three recommendation statuses (PLAN §5.7). Nothing is ever labelled Recommended unless status is `recommended`. */
export function RecommendationBanner({ plan }: { plan: PlanResponse }) {
  const { recommendation: rec, routes } = plan;

  if (rec.status === 'recommended') {
    return (
      <section
        aria-labelledby="rec-heading"
        data-status="recommended"
        className="rounded-xl border-2 border-emerald-700 bg-emerald-50 p-3"
      >
        <h2 id="rec-heading" className="text-base font-bold text-emerald-950">
          <span aria-hidden="true">★ </span>
          {rec.headline}
        </h2>
        {rec.reasons.length > 0 ? (
          <ul className="mt-1 list-disc pl-5 text-sm text-emerald-950">
            {rec.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : null}
        {rec.caveats.length > 0 ? (
          <ul className="mt-2 list-none space-y-0.5 text-sm text-amber-950">
            {rec.caveats.map((c) => (
              <li key={c}>
                <span aria-hidden="true">⚠ </span>
                {c}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    );
  }

  if (rec.status === 'no_safe_route') {
    return (
      <section
        aria-labelledby="rec-heading"
        data-status="no_safe_route"
        className="rounded-xl border-2 border-red-800 bg-red-50 p-3"
      >
        <h2 id="rec-heading" className="text-base font-bold text-red-950">
          <span aria-hidden="true">⊘ </span>
          {NO_SAFE_ROUTE_HEADLINE}
        </h2>
        <p className="mt-1 text-sm text-red-950">
          Every returned route has No Travel conditions. Routes and hazards are shown for reference — none is
          recommended.
        </p>
        {rec.reasons.length > 0 ? (
          <ul className="mt-1 list-disc pl-5 text-sm text-red-950">
            {rec.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : null}
      </section>
    );
  }

  return (
    <section
      aria-labelledby="rec-heading"
      data-status="inconclusive"
      className="rounded-xl border-2 border-amber-700 bg-amber-50 p-3"
    >
      <h2 id="rec-heading" className="text-base font-bold text-amber-950">
        <span aria-hidden="true">? </span>
        {INCONCLUSIVE_HEADLINE}
      </h2>
      <p className="mt-1 text-sm text-amber-950">
        The weather forecast does not cover every route completely, so no route can be called safe. Unknown
        sections are never treated as Low risk.
      </p>
      <ul className="mt-1 list-disc pl-5 text-sm text-amber-950">
        {routes.map((r) => (
          <li key={r.id}>
            {r.name}: forecast covers {formatPercent(r.summary.coverage_pct)} of the route
          </li>
        ))}
      </ul>
    </section>
  );
}
