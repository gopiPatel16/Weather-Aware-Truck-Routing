import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { CHICAGO, DENVER, heatmap, inconclusive, jsonResponse, noSafeRoute, storm } from './test/fixtures';
import type { PlanResponse } from './api/types';

// The real map needs WebGL; its inputs are what matters here.
const mapProps = vi.hoisted(() => ({ latest: null as Record<string, unknown> | null }));
vi.mock('./components/MapView', () => ({
  MapView: (props: Record<string, unknown>) => {
    mapProps.latest = props;
    return <div data-testid="map" />;
  },
}));

const fetchMock = vi.fn();
const initialTrip = { origin: CHICAGO, destination: DENVER, cargoWeight: '42000' };

function stubApi(plan: PlanResponse, heat: 'ok' | 'fail' = 'ok') {
  fetchMock.mockImplementation(async (url: string) => {
    if (url === '/api/plan') return jsonResponse(plan);
    if (url === '/api/heatmap')
      return heat === 'ok'
        ? jsonResponse(heatmap())
        : jsonResponse({ error: { code: 'weather_unavailable', message: 'Forecast service down.' } }, 400);
    return jsonResponse({ results: [] });
  });
}

const plan = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole('button', { name: 'Find safest route' }));
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('App', () => {
  it('plans a trip, shows the recommendation and routes, and loads the heatmap exactly once', async () => {
    stubApi(storm());
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);

    expect(
      await screen.findByRole('heading', { name: /Route C is the safest eligible route/ }),
    ).toBeInTheDocument();
    expect(screen.getByText('3 routes')).toBeInTheDocument();
    // Recommended route is pre-selected and its checkpoint table is shown.
    expect(screen.getByRole('button', { name: /Route C/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: /Checkpoints — Route C/ })).toBeInTheDocument();

    const slider = await screen.findByRole('slider');
    await waitFor(() => expect(slider).toBeEnabled());
    const calls = () => fetchMock.mock.calls.map((c) => c[0]);
    expect(calls().filter((u) => u === '/api/plan')).toHaveLength(1);
    expect(calls().filter((u) => u === '/api/heatmap')).toHaveLength(1);

    // Scrub through the whole range: no further requests, the map just gets the new hour.
    const before = fetchMock.mock.calls.length;
    for (const h of [5, 12, 30, 48, 0]) {
      fireEvent.change(slider, { target: { value: String(h) } });
      expect(mapProps.latest?.hour).toBe(h);
    }
    expect(fetchMock.mock.calls.length).toBe(before);
  });

  it("sends the cargo weight and routes' polylines to the heatmap endpoint", async () => {
    stubApi(storm());
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);
    await screen.findByRole('slider');
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => c[0] === '/api/heatmap')).toBe(true));
    const [, init] = fetchMock.mock.calls.find((c) => c[0] === '/api/heatmap')!;
    const body = JSON.parse(init.body as string);
    expect(body.cargo_weight_lb).toBe(42000);
    expect(body.routes.map((r: { id: string }) => r.id)).toEqual(['A', 'B', 'C']);
    expect(body.routes[0].polyline).toBe(storm().routes[0]!.polyline);
    expect(body.departure_utc).toBe('2026-11-02T12:00:00Z');
  });

  it('clicking a checkpoint moves the slider to its ETA hour (within 0–48 h)', async () => {
    stubApi(storm());
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);
    await screen.findByRole('heading', { name: /Checkpoints — Route C/ });
    await waitFor(() => expect(screen.getByRole('slider')).toBeEnabled());

    // Route C checkpoint at mile 250: ETA ≈ departure + 4 h.
    const route = storm().routes[2]!;
    const cp = route.checkpoints.find((c) => c.mile === 250)!;
    const expected = Math.round((Date.parse(cp.eta_utc) - Date.parse('2026-11-02T12:00:00Z')) / 3_600_000);
    await user.click(screen.getByRole('button', { name: 'Show checkpoint at mile 250 on the map' }));
    expect(screen.getByRole('slider')).toHaveValue(String(expected));
    expect(mapProps.latest?.checkpoint).toMatchObject({ routeId: 'C', index: cp.i });
  });

  it('keeps routes usable when the heatmap fails and offers a retry', async () => {
    stubApi(storm(), 'fail');
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);
    expect(await screen.findByText(/Forecast overview unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Route C is the safest eligible route/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry heatmap' })).toBeInTheDocument();
  });

  it('all routes blocked: "No safe route available", nothing marked Recommended', async () => {
    stubApi(noSafeRoute());
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);
    expect(await screen.findByRole('heading', { name: 'No safe route available' })).toBeInTheDocument();
    expect(screen.queryByText('★ Recommended')).not.toBeInTheDocument();
    expect(mapProps.latest?.recommendedId).toBeNull();
    for (const card of screen.getAllByRole('button', { name: /^Route [ABC]/ })) {
      expect(card).toHaveTextContent('Not eligible');
    }
  });

  it('incomplete weather: "A safe recommendation cannot be determined"', async () => {
    stubApi(inconclusive());
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);
    expect(
      await screen.findByRole('heading', { name: 'A safe recommendation cannot be determined' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('★ Recommended')).not.toBeInTheDocument();
    // Unknown checkpoints appear as Unknown (never Low) in the table.
    const table = screen.getByRole('table');
    expect(within(table).getAllByText('Unknown', { exact: false }).length).toBeGreaterThan(0);
  });

  it('shows an API error with a manual Retry (no retry for a 400)', async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse(
        {
          error: {
            code: 'validation_error',
            message: 'Some fields are invalid.',
            fields: { cargo_weight_lb: ['Too low.'] },
          },
        },
        400,
      ),
    );
    const user = userEvent.setup();
    render(<App initialTrip={initialTrip} />);
    await plan(user);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Check the trip details');
    expect(alert).toHaveTextContent('cargo weight lb: Too low.');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('opens the Rules drawer with the exact threshold tables', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Rules' }));
    const dialog = screen.getByRole('dialog', { hidden: true });
    expect(within(dialog).getByText('0.50 ≤ x ≤ 1.00')).toBeInTheDocument();
    expect(within(dialog).getByText('x > 3.0')).toBeInTheDocument();
    expect(within(dialog).getByText('cargo > 30,000 lb')).toBeInTheDocument();
  });
});
