import { useEffect, useRef, useState } from 'react';
import type { Route } from '../api/types';
import type { MapController, PinSpec } from '../map/MapController';
import type { HeatmapData } from '../utils/heatmap';

export interface SelectedCheckpoint {
  routeId: string;
  index: number;
  /** True when the selection came from the table/slider, so the map should pan to it. */
  pan: boolean;
}

interface Props {
  routes: Route[];
  selectedRouteId: string | null;
  recommendedId: string | null;
  departureUtc: string;
  pins: PinSpec[];
  checkpoint: SelectedCheckpoint | null;
  heatmap: HeatmapData | null;
  hour: number;
  heatVisible: boolean;
  onCheckpointClick: (routeId: string, index: number) => void;
  onRouteClick: (routeId: string) => void;
  onPopupClose: () => void;
}

/** Hosts the MapLibre controller. The map library is loaded lazily so it stays out of the initial bundle. */
export function MapView(props: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<MapController | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const handlers = useRef(props);
  useEffect(() => {
    handlers.current = props;
  });

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;
    (async () => {
      try {
        const [maplibre, { MapController }, worker] = await Promise.all([
          import('maplibre-gl'),
          import('../map/MapController'),
          // MapLibre 6 locates its worker with `new URL(…, import.meta.url)`, which Vite does not rewrite
          // for a pre-bundled / chunked dependency. Hand it the emitted asset URL explicitly.
          import('maplibre-gl/dist/maplibre-gl-worker.mjs?url'),
          import('maplibre-gl/dist/maplibre-gl.css'),
        ]);
        if (cancelled) return;
        maplibre.setWorkerUrl(worker.default);
        controllerRef.current = new MapController({
          container,
          maplibre,
          styleUrl: import.meta.env.VITE_MAP_STYLE_URL,
          callbacks: {
            onCheckpointClick: (r, i) => handlers.current.onCheckpointClick(r, i),
            onRouteClick: (r) => handlers.current.onRouteClick(r),
            onPopupClose: () => handlers.current.onPopupClose(),
          },
        });
        setReady(true);
      } catch (e) {
        if (!cancelled) setFailed(e instanceof Error ? e.message : 'unknown error');
      }
    })();
    const ro = new ResizeObserver(() => controllerRef.current?.resize());
    ro.observe(container);
    return () => {
      cancelled = true;
      ro.disconnect();
      controllerRef.current?.destroy();
      controllerRef.current = null;
      setReady(false);
    };
  }, []);

  const {
    routes,
    selectedRouteId,
    recommendedId,
    departureUtc,
    pins,
    checkpoint,
    heatmap,
    hour,
    heatVisible,
  } = props;

  useEffect(() => {
    if (ready)
      controllerRef.current?.setRoutes(routes, selectedRouteId, recommendedId, departureUtc, pins, true);
    // Route selection is handled separately so picking another route does not re-fit the map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, routes, recommendedId, departureUtc, pins]);

  useEffect(() => {
    if (ready) controllerRef.current?.setSelectedRoute(selectedRouteId);
  }, [ready, selectedRouteId]);

  useEffect(() => {
    if (ready)
      controllerRef.current?.setSelectedCheckpoint(
        checkpoint?.routeId ?? null,
        checkpoint?.index ?? null,
        checkpoint?.pan ?? false,
      );
  }, [ready, checkpoint, routes]);

  useEffect(() => {
    if (ready) controllerRef.current?.setHeatmap(heatmap);
  }, [ready, heatmap]);

  useEffect(() => {
    if (ready) controllerRef.current?.setHour(hour);
  }, [ready, hour]);

  useEffect(() => {
    if (ready) controllerRef.current?.setHeatVisible(heatVisible);
  }, [ready, heatVisible]);

  return (
    <div className="relative size-full">
      <div ref={containerRef} className="size-full" role="region" aria-label="Route map" />
      {failed ? (
        <div
          role="alert"
          className="absolute inset-0 grid place-items-center bg-slate-100 p-6 text-center text-sm"
        >
          <p>
            The map could not be started ({failed}). Routes, checkpoints and the rules are still available in
            the panel.
          </p>
        </div>
      ) : null}
    </div>
  );
}
