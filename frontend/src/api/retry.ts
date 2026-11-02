import { ApiError, isAbortError } from './errors';

/** Back-off between automatic retries (PLAN §8): 2 s, 5 s, 10 s. */
export const RETRY_DELAYS_MS = [2000, 5000, 10000] as const;

export interface RetryInfo {
  /** 1-based number of the upcoming retry. */
  attempt: number;
  of: number;
  delayMs: number;
  error: ApiError;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

/**
 * Runs `task`, retrying transient failures (network error, 502/503/504) after 2 s, 5 s and 10 s.
 * Other errors, and aborts, propagate immediately.
 */
export async function withRetry<T>(
  task: (signal: AbortSignal) => Promise<T>,
  signal: AbortSignal,
  onRetry?: (info: RetryInfo) => void,
  delays: readonly number[] = RETRY_DELAYS_MS,
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await task(signal);
    } catch (e) {
      if (isAbortError(e) || !(e instanceof ApiError) || !e.isTransient || attempt >= delays.length) throw e;
      const delayMs = delays[attempt] ?? 0;
      onRetry?.({ attempt: attempt + 1, of: delays.length, delayMs, error: e });
      await sleep(delayMs, signal);
    }
  }
}
