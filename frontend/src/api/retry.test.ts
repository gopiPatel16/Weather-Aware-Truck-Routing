import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './errors';
import { RETRY_DELAYS_MS, withRetry } from './retry';

const transient = (status = 503) => new ApiError({ status, code: 'routing_unavailable', message: 'busy' });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('withRetry', () => {
  it('retries at 2 s, 5 s and 10 s then succeeds', async () => {
    expect(RETRY_DELAYS_MS).toEqual([2000, 5000, 10000]);
    const task = vi
      .fn<(s: AbortSignal) => Promise<string>>()
      .mockRejectedValueOnce(transient(503))
      .mockRejectedValueOnce(transient(502))
      .mockRejectedValueOnce(new ApiError({ status: 0, code: 'network_error', message: 'offline' }))
      .mockResolvedValueOnce('ok');
    const onRetry = vi.fn();
    const p = withRetry(task, new AbortController().signal, onRetry);

    await vi.advanceTimersByTimeAsync(0);
    expect(task).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1999);
    expect(task).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(task).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(task).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(10000);
    await expect(p).resolves.toBe('ok');
    expect(task).toHaveBeenCalledTimes(4);
    expect(onRetry.mock.calls.map(([i]) => [i.attempt, i.of, i.delayMs])).toEqual([
      [1, 3, 2000],
      [2, 3, 5000],
      [3, 3, 10000],
    ]);
  });

  it('gives up after the third retry and surfaces the last error', async () => {
    const task = vi.fn().mockRejectedValue(transient(504));
    const p = withRetry(task, new AbortController().signal);
    const assertion = expect(p).rejects.toMatchObject({ status: 504 });
    await vi.advanceTimersByTimeAsync(2000 + 5000 + 10000);
    await assertion;
    expect(task).toHaveBeenCalledTimes(4);
  });

  it.each([400, 422, 429])('does not retry HTTP %i', async (status) => {
    const task = vi.fn().mockRejectedValue(new ApiError({ status, code: 'validation_error', message: 'no' }));
    await expect(withRetry(task, new AbortController().signal)).rejects.toMatchObject({ status });
    expect(task).toHaveBeenCalledTimes(1);
  });

  it('stops waiting when aborted', async () => {
    const controller = new AbortController();
    const task = vi.fn().mockRejectedValue(transient());
    const p = withRetry(task, controller.signal);
    const assertion = expect(p).rejects.toMatchObject({ name: 'AbortError' });
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();
    await assertion;
    expect(task).toHaveBeenCalledTimes(1);
  });
});
