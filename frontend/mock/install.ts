import type { PlanRequest } from '../src/api/types';
import {
  SCENARIO_IDS,
  geocodeReply,
  heatmapReply,
  planReply,
  type MockReply,
  type ScenarioId,
  type ScenarioState,
} from './scenarios';

/** Simulated latency so loading states are visible. */
const LATENCY_MS = { plan: 1800, heatmap: 700, geocode: 150 } as const;

type Listener = (id: ScenarioId) => void;

const initial = new URLSearchParams(globalThis.location?.search ?? '').get('scenario');
let current: ScenarioId = SCENARIO_IDS.find((id) => id === initial) ?? 'normal';
let state: ScenarioState = { planCalls: 0 };
const listeners = new Set<Listener>();

export const getScenario = (): ScenarioId => current;

export function setScenario(id: ScenarioId): void {
  current = id;
  state = { planCalls: 0 };
  listeners.forEach((l) => l(id));
}

export function subscribeScenario(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function wait(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function toResponse(reply: MockReply): Response {
  return new Response(JSON.stringify(reply.body), {
    status: reply.status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function handle(url: URL, init: RequestInit | undefined): Promise<Response> {
  const signal = init?.signal;
  if (url.pathname === '/api/health/') return toResponse({ status: 200, body: { status: 'ok' } });
  if (url.pathname === '/api/geocode') {
    await wait(LATENCY_MS.geocode, signal);
    return toResponse(geocodeReply(url.searchParams.get('q') ?? ''));
  }
  if (url.pathname === '/api/plan') {
    await wait(LATENCY_MS.plan, signal);
    const req = typeof init?.body === 'string' ? (JSON.parse(init.body) as PlanRequest) : null;
    return toResponse(planReply(current, req, state));
  }
  if (url.pathname === '/api/heatmap') {
    await wait(LATENCY_MS.heatmap, signal);
    return toResponse(heatmapReply(current));
  }
  return toResponse({
    status: 404,
    body: { error: { code: 'not_found', message: 'Unknown mock endpoint.' } },
  });
}

/** Replaces `window.fetch` for `/api/*` calls; every other request passes through untouched. */
export function installMockApi(): void {
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, window.location.origin);
    return url.pathname.startsWith('/api/') ? handle(url, init) : realFetch(input, init);
  };
}
