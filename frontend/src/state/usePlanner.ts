import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { ApiError, isAbortError } from '../api/errors';
import { withRetry, type RetryInfo } from '../api/retry';
import type { PlanRequest, PlanResponse } from '../api/types';

export interface RetryState {
  info: RetryInfo;
  /** `Date.now()` when the wait began, so the UI can count down. */
  startedAt: number;
}

export type PlannerState =
  | { phase: 'idle' }
  | { phase: 'loading'; request: PlanRequest; retry: RetryState | null }
  | { phase: 'success'; request: PlanRequest; plan: PlanResponse }
  | { phase: 'error'; request: PlanRequest; error: ApiError };

/**
 * Plain-hooks planner: one in-flight request at a time (a new submit aborts the previous),
 * transient failures retried automatically at 2 s / 5 s / 10 s, and a manual `retry`.
 */
export function usePlanner() {
  const [state, setState] = useState<PlannerState>({ phase: 'idle' });
  const abortRef = useRef<AbortController | null>(null);
  const lastRequest = useRef<PlanRequest | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const submit = useCallback(async (request: PlanRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    lastRequest.current = request;
    setState({ phase: 'loading', request, retry: null });
    try {
      const plan = await withRetry(
        (signal) => api.plan(request, signal),
        controller.signal,
        (info) => setState({ phase: 'loading', request, retry: { info, startedAt: Date.now() } }),
      );
      if (controller.signal.aborted) return;
      setState({ phase: 'success', request, plan });
    } catch (e) {
      if (isAbortError(e) || controller.signal.aborted) return;
      const error =
        e instanceof ApiError
          ? e
          : new ApiError({
              status: 0,
              code: 'network_error',
              message: 'Something went wrong. Please try again.',
            });
      setState({ phase: 'error', request, error });
    }
  }, []);

  const retry = useCallback(() => {
    if (lastRequest.current) void submit(lastRequest.current);
  }, [submit]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState({ phase: 'idle' });
  }, []);

  return { state, submit, retry, cancel };
}
