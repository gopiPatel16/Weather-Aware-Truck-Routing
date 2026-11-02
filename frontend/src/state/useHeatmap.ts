import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { ApiError, isAbortError } from '../api/errors';
import { withRetry } from '../api/retry';
import type { PlanResponse } from '../api/types';
import { decodeHeatmap, type HeatmapData } from '../utils/heatmap';

export type HeatmapState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'ready'; data: HeatmapData }
  | { phase: 'error'; message: string };

interface Settled {
  plan: PlanResponse;
  attempt: number;
  state: Extract<HeatmapState, { phase: 'ready' | 'error' }>;
}

/**
 * Loads the 0–48 h heatmap once per plan. All 49 hours arrive in this single response, so moving the
 * slider afterwards never touches the network. A failure leaves the routes fully usable.
 */
export function useHeatmap(plan: PlanResponse | null) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);

  useEffect(() => {
    if (!plan) return;
    const controller = new AbortController();
    withRetry(
      (signal) =>
        api.heatmap(
          {
            routes: plan.routes.map((r) => ({ id: r.id, polyline: r.polyline })),
            departure_utc: plan.request.departure_utc,
            cargo_weight_lb: plan.request.cargo_weight_lb,
          },
          signal,
        ),
      controller.signal,
    )
      .then((resp) => setSettled({ plan, attempt, state: { phase: 'ready', data: decodeHeatmap(resp) } }))
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        const message = e instanceof ApiError ? e.message : 'The heatmap could not be loaded.';
        setSettled({ plan, attempt, state: { phase: 'error', message } });
      });
    return () => controller.abort();
  }, [plan, attempt]);

  // Derived during render: a result only counts for the plan/attempt it was fetched for.
  let state: HeatmapState = { phase: 'idle' };
  if (plan) {
    state =
      settled && settled.plan === plan && settled.attempt === attempt ? settled.state : { phase: 'loading' };
  }

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, reload };
}
