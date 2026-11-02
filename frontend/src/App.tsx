import { useCallback, useMemo, useState, type ReactNode } from 'react';
import type { PlanRequest, Route } from './api/types';
import { CheckpointTable } from './components/CheckpointTable';
import { Footer } from './components/Footer';
import { HeatmapPanel } from './components/HeatmapPanel';
import { Legend } from './components/Legend';
import { MapView, type SelectedCheckpoint } from './components/MapView';
import { PlanNotices } from './components/PlanNotices';
import { RecommendationBanner } from './components/RecommendationBanner';
import { RouteCard } from './components/RouteCard';
import { RulesDrawer } from './components/RulesDrawer';
import { ErrorPanel, LoadingPanel } from './components/StatusPanels';
import { TripForm, type TripFormInitial } from './components/TripForm';
import type { PinSpec } from './map/MapController';
import { useHeatmap } from './state/useHeatmap';
import { usePlanner } from './state/usePlanner';
import { formatDuration } from './utils/format';
import { etaHourOffset } from './utils/time';

type Sheet = 'peek' | 'half' | 'full';
const SHEET_CLASS: Record<Sheet, string> = {
  peek: 'h-[92px]',
  half: 'h-[46dvh]',
  full: 'h-[calc(100dvh-52px)]',
};
const NEXT_SHEET: Record<Sheet, Sheet> = { peek: 'half', half: 'full', full: 'peek' };

interface Props {
  /** Demo defaults and the scenario picker, supplied only in mock mode. */
  initialTrip?: TripFormInitial;
  devTools?: ReactNode;
}

const pin = (kind: PinSpec['kind'], p: PlanRequest['origin']): PinSpec => ({
  kind,
  label: p.label,
  lngLat: [p.lon, p.lat],
});

export default function App({ initialTrip, devTools }: Props) {
  const planner = usePlanner();
  const [userRouteId, setUserRouteId] = useState<string | null>(null);
  const [checkpoint, setCheckpoint] = useState<SelectedCheckpoint | null>(null);
  const [hour, setHour] = useState(0);
  const [heatVisible, setHeatVisible] = useState(true);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [sheet, setSheet] = useState<Sheet>('half');
  const [formOpen, setFormOpen] = useState(true);

  const result = planner.state.phase === 'success' ? planner.state : null;
  const plan = result?.plan ?? null;
  const heatmap = useHeatmap(plan);

  const routes: Route[] = useMemo(() => plan?.routes ?? [], [plan]);
  const recommendedId = plan?.recommendation.status === 'recommended' ? plan.recommendation.route_id : null;
  const defaultRouteId = recommendedId ?? routes[0]?.id ?? null;
  const selectedRouteId =
    userRouteId && routes.some((r) => r.id === userRouteId) ? userRouteId : defaultRouteId;
  const selectedRoute = routes.find((r) => r.id === selectedRouteId);
  const fastest = routes.reduce((min, r) => Math.min(min, r.duration_s), Infinity);

  const request = planner.state.phase === 'idle' ? null : planner.state.request;
  const pins = useMemo(
    () => (request && plan ? [pin('start', request.origin), pin('end', request.destination)] : []),
    [request, plan],
  );

  const submit = useCallback(
    (req: PlanRequest) => {
      setUserRouteId(null);
      setCheckpoint(null);
      setHour(0);
      setSheet('half');
      void planner.submit(req);
    },
    [planner],
  );

  // After the first results arrive, tuck the form away on small screens so the results get the room.
  const [lastPlan, setLastPlan] = useState<typeof plan>(null);
  if (plan !== lastPlan) {
    setLastPlan(plan);
    if (plan && window.matchMedia?.('(max-width: 899px)').matches) setFormOpen(false);
  }

  const selectRoute = useCallback((id: string) => {
    setUserRouteId(id);
    setCheckpoint(null);
  }, []);

  const selectCheckpoint = useCallback(
    (routeId: string, index: number, pan: boolean) => {
      const route = routes.find((r) => r.id === routeId);
      const cp = route?.checkpoints.find((c) => c.i === index);
      setUserRouteId(routeId);
      setCheckpoint({ routeId, index, pan });
      if (cp && plan) {
        const h = etaHourOffset(plan.request.departure_utc, cp.eta_utc);
        if (h !== null) setHour(h);
      }
    },
    [routes, plan],
  );

  const onMapCheckpoint = useCallback(
    (routeId: string, index: number) => selectCheckpoint(routeId, index, false),
    [selectCheckpoint],
  );
  const onTableCheckpoint = useCallback(
    (routeId: string, index: number) => selectCheckpoint(routeId, index, true),
    [selectCheckpoint],
  );
  const onPopupClose = useCallback(() => setCheckpoint(null), []);

  const peekSummary = useMemo(() => {
    switch (planner.state.phase) {
      case 'loading':
        return 'Planning your trip…';
      case 'error':
        return 'Could not plan the trip — expand for details';
      case 'success': {
        const rec = planner.state.plan.recommendation;
        if (rec.status === 'recommended') {
          const r = planner.state.plan.routes.find((x) => x.id === rec.route_id);
          return `★ ${r?.name ?? 'Route'} recommended${r ? ` · ${formatDuration(r.duration_s)}` : ''}`;
        }
        return rec.headline;
      }
      default:
        return 'Plan a trip';
    }
  }, [planner.state]);

  const busy = planner.state.phase === 'loading';
  const hasMapData = routes.length > 0;
  const departureUtc = plan?.request.departure_utc ?? '';

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-[52px] shrink-0 items-center gap-3 bg-brand px-4 text-white">
        <h1 className="truncate text-base font-bold lg:text-lg">
          <span className="lg:hidden">Truck Routing</span>
          <span className="hidden lg:inline">Weather-Aware Truck Routing</span>
        </h1>
        <div className="ml-auto flex items-center gap-2">
          {devTools}
          <button
            type="button"
            onClick={() => setRulesOpen(true)}
            className="rounded-md border border-white/60 px-3 py-1 text-sm font-medium hover:bg-white/15"
          >
            Rules
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="relative min-h-0 flex-1 lg:order-2" aria-label="Map">
          <MapView
            routes={routes}
            selectedRouteId={selectedRouteId}
            recommendedId={recommendedId}
            departureUtc={departureUtc}
            pins={pins}
            checkpoint={checkpoint}
            heatmap={heatmap.state.phase === 'ready' ? heatmap.state.data : null}
            hour={hour}
            heatVisible={heatVisible}
            onCheckpointClick={onMapCheckpoint}
            onRouteClick={selectRoute}
            onPopupClose={onPopupClose}
          />
          <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-start p-2">
            <details
              open={false}
              className="pointer-events-auto max-w-[19rem] rounded-xl border border-line bg-white/95 p-2 shadow-lg backdrop-blur lg:open:block"
            >
              <summary className="cursor-pointer text-sm font-semibold">Legend</summary>
              <div className="mt-2">
                <Legend />
              </div>
            </details>
          </div>
          {hasMapData && plan ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-8 flex justify-center px-2">
              <HeatmapPanel
                state={heatmap.state}
                hour={hour}
                startUtc={plan.request.departure_utc}
                originTimeZone={plan.request.origin_timezone}
                heatVisible={heatVisible}
                onHourChange={setHour}
                onHeatVisibleChange={setHeatVisible}
                onRetry={heatmap.reload}
              />
            </div>
          ) : null}
        </main>

        <aside
          aria-label="Trip planner and results"
          className={`flex shrink-0 flex-col overflow-hidden rounded-t-2xl border-t border-line bg-surface shadow-[0_-4px_16px_rgb(0_0_0/0.15)] lg:order-1 lg:h-auto lg:w-[440px] lg:rounded-none lg:border-r lg:border-t-0 lg:shadow-none ${SHEET_CLASS[sheet]}`}
        >
          <button
            type="button"
            onClick={() => setSheet(NEXT_SHEET[sheet])}
            aria-expanded={sheet !== 'peek'}
            aria-label={`Results panel is ${sheet === 'peek' ? 'collapsed' : sheet === 'half' ? 'half open' : 'fully open'}. Activate to ${sheet === 'full' ? 'collapse' : 'expand'}.`}
            className="flex w-full shrink-0 flex-col items-center gap-1 px-4 pb-1 pt-2 lg:hidden"
          >
            <span aria-hidden="true" className="h-1.5 w-12 rounded-full bg-slate-400" />
            <span className="text-sm font-semibold">{peekSummary}</span>
          </button>

          <div className="flex-1 space-y-3 overflow-y-auto px-3 pb-6 pt-2 lg:p-4">
            {formOpen ? (
              <TripForm busy={busy} initial={initialTrip} onSubmit={submit} />
            ) : (
              <div className="flex items-center justify-between rounded-xl border border-line bg-white p-3 text-sm">
                <span className="truncate">
                  {request?.origin.label} → {request?.destination.label}
                </span>
                <button
                  type="button"
                  onClick={() => setFormOpen(true)}
                  className="ml-2 shrink-0 rounded-md border border-slate-500 px-2.5 py-1 text-xs font-semibold hover:bg-slate-100"
                >
                  Edit trip
                </button>
              </div>
            )}

            <div aria-live="polite" aria-atomic="false" className="space-y-3">
              {planner.state.phase === 'loading' ? (
                <LoadingPanel
                  retry={planner.state.retry}
                  onCancel={planner.cancel}
                  onRetryNow={planner.retry}
                />
              ) : null}
              {planner.state.phase === 'error' ? (
                <ErrorPanel error={planner.state.error} onRetry={planner.retry} />
              ) : null}
              {plan && result ? (
                <>
                  <RecommendationBanner plan={plan} />
                  <PlanNotices plan={plan} />
                  <h2 className="pt-1 text-sm font-bold">
                    {routes.length === 1 ? '1 route' : `${routes.length} routes`}
                  </h2>
                  {routes.length === 0 ? (
                    <p className="rounded-lg border border-line bg-white p-3 text-sm">
                      No truck routes were returned for this trip. Try different locations.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {routes.map((r, i) => (
                        <RouteCard
                          key={r.id}
                          route={r}
                          index={i}
                          selected={r.id === selectedRouteId}
                          recommended={r.id === recommendedId}
                          slowerBySeconds={r.duration_s - fastest}
                          onSelect={selectRoute}
                        />
                      ))}
                    </ul>
                  )}
                </>
              ) : null}
            </div>

            {selectedRoute && result ? (
              <CheckpointTable
                route={selectedRoute}
                intervalMiles={plan?.request.interval_miles ?? result.request.interval_miles}
                selectedIndex={checkpoint?.routeId === selectedRoute.id ? checkpoint.index : null}
                onSelect={onTableCheckpoint}
              />
            ) : null}

            <Footer />
          </div>
        </aside>
      </div>

      <RulesDrawer open={rulesOpen} onClose={() => setRulesOpen(false)} />
    </div>
  );
}
