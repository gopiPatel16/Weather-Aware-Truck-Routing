import type { ErrorCode } from './types';

/** Error raised by the typed client; `status` is 0 for network failures. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode;
  readonly retryAfterS?: number;
  readonly fields?: Record<string, string[]>;

  constructor(init: {
    status: number;
    code: ErrorCode;
    message: string;
    retryAfterS?: number;
    fields?: Record<string, string[]>;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.retryAfterS = init.retryAfterS;
    this.fields = init.fields;
  }

  /** Worth retrying automatically: the server is waking up or briefly overloaded. */
  get isTransient(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

export const isAbortError = (e: unknown): boolean => e instanceof DOMException && e.name === 'AbortError';
