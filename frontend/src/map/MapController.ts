import type * as maplibregl from 'maplibre-gl';
import type {
  ExpressionSpecification,
  GeoJSONSource,
  LngLatBoundsLike,
  Map as MapLibreMap,
  Marker,
  Popup,
  StyleSpecification,
} from 'maplibre-gl';
import type { Checkpoint, Route } from '../api/types';
import { HEAT_WEIGHTS, RISK_STYLES } from '../utils/risk';
import {
  toFeatureCollection,
  unknownOpacityExpression,
  weightExpression,
  type HeatmapData,
} from '../utils/heatmap';
import { boundsOf, pointAlong, type LngLat } from './geometry';
import { buildCheckpointPopup } from './popup';
import { checkpointPoints, routeLines, selectedSegments } from './sources';
import { formatDuration, formatMiles } from '../utils/format';

type MapLibre = typeof maplibregl;

export const ATTRIBUTION = [
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>',
  '<a href="https://openmaptiles.org/" target="_blank" rel="noopener">© OpenMapTiles</a>',
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a>',
];

const DEFAULT_STYLE = 'https://tiles.openfreemap.org/styles/positron';

const SRC = {
  routes: 'routes',
  segments: 'selected-segments',
  checkpoints: 'checkpoints',
  heat: 'heat',
} as const;

const LAYER = {
  heat: 'heat-overview',
  heatUnknown: 'heat-unknown',
  routeCasing: 'route-casing',
  routeLine: 'route-line',
  routeHit: 'route-hit',
  segCasing: 'segments-casing',
  segLine: 'segments-line',
  segUnknown: 'segments-unknown',
  cpCircle: 'checkpoint-circles',
  cpLetter: 'checkpoint-letters',
  cpHalo: 'checkpoint-selected',
} as const;

const levelMatch = (
  prop: string,
  pick: (l: keyof typeof RISK_STYLES) => string | number,
  fallback: string | number,
) =>
  [
    'match',
    ['get', prop],
    ...(Object.keys(RISK_STYLES) as (keyof typeof RISK_STYLES)[]).flatMap((l) => [l, pick(l)]),
    fallback,
  ] as unknown as ExpressionSpecification;

const RISK_COLOR = levelMatch('level', (l) => RISK_STYLES[l].color, '#7c8591');

/** Heat ramp is calibrated so an interior of uniform weight w renders as the colour of that level. */
const HEAT_COLOR = [
  'interpolate',
  ['linear'],
  ['heatmap-density'],
  0,
  'rgba(47,158,95,0)',
  HEAT_WEIGHTS.low * 0.5,
  'rgba(47,158,95,0.25)',
  HEAT_WEIGHTS.low,
  'rgba(47,158,95,0.45)',
  HEAT_WEIGHTS.moderate,
  'rgba(229,177,0,0.62)',
  HEAT_WEIGHTS.high,
  'rgba(240,138,28,0.7)',
  HEAT_WEIGHTS.severe,
  'rgba(217,45,32,0.76)',
  HEAT_WEIGHTS.no_travel,
  'rgba(43,15,77,0.82)',
] as unknown as ExpressionSpecification;

export interface MapCallbacks {
  onCheckpointClick: (routeId: string, index: number) => void;
  onRouteClick: (routeId: string) => void;
  /** Called when the user closes the checkpoint popup. */
  onPopupClose: () => void;
}

export interface MapInit {
  container: HTMLElement;
  styleUrl?: string;
  maplibre: MapLibre;
  callbacks: MapCallbacks;
}

export interface PinSpec {
  label: string;
  kind: 'start' | 'end';
  lngLat: LngLat;
}

const empty = { type: 'FeatureCollection', features: [] } as const;

/**
 * Thin lifecycle wrapper around a MapLibre map. React hands it plain data through `set*` methods;
 * it owns sources, layers, markers and the popup, and applies slider changes at most once per frame.
 */
export class MapController {
  private readonly ml: MapLibre;
  private readonly map: MapLibreMap;
  private readonly callbacks: MapCallbacks;
  private loaded = false;
  private destroyed = false;
  private pending: Array<() => void> = [];

  private routes: Route[] = [];
  private selectedId: string | null = null;
  private departureUtc = '';
  private chipMarkers: Marker[] = [];
  private pinMarkers: Marker[] = [];
  private popup: Popup | null = null;
  private suppressPopupClose = false;
  private pinSpecs: PinSpec[] = [];
  private recommendedId: string | null = null;

  private pendingHour = 0;
  private appliedHour = -1;
  private raf = 0;

  constructor(init: MapInit) {
    this.ml = init.maplibre;
    this.callbacks = init.callbacks;
    const style: string | StyleSpecification = init.styleUrl || DEFAULT_STYLE;
    this.map = new this.ml.Map({
      container: init.container,
      style,
      center: [-98, 39],
      zoom: 3.4,
      attributionControl: false,
      cooperativeGestures: false,
    });
    // Dev aid: lets you poke at the map from the browser console.
    if (import.meta.env.DEV) Object.assign(window, { __map: this.map });
    this.map.addControl(new this.ml.NavigationControl({ showCompass: false }), 'top-right');
    this.map.once('style.load', () => {
      if (this.destroyed) return;
      // Credit OSM / OpenMapTiles / OpenFreeMap ourselves unless the style's own sources already do.
      const styled = Object.values(this.map.getStyle().sources).some(
        (s) => 'attribution' in s && Boolean(s.attribution),
      );
      // Narrow maps get the collapsed (i) button so the credits never cover the slider card.
      const compact = init.container.clientWidth < 640;
      this.map.addControl(
        new this.ml.AttributionControl({ compact, customAttribution: styled ? [] : ATTRIBUTION }),
        'bottom-right',
      );
      if (compact) {
        const credits = init.container.querySelector('.maplibregl-ctrl-attrib');
        credits?.classList.remove('maplibregl-compact-show');
        credits?.removeAttribute('open');
      }
      this.addSourcesAndLayers();
      this.loaded = true;
      this.pending.splice(0).forEach((fn) => fn());
    });
  }

  private whenReady(fn: () => void): void {
    if (this.loaded) fn();
    else this.pending.push(fn);
  }

  /** First symbol layer of the basemap, so overlays sit beneath place labels. */
  private labelLayerId(): string | undefined {
    return this.map.getStyle().layers.find((l) => l.type === 'symbol')?.id;
  }

  private addSourcesAndLayers(): void {
    const map = this.map;
    const before = this.labelLayerId();
    for (const id of Object.values(SRC)) map.addSource(id, { type: 'geojson', data: empty as never });

    // 1. Smoothed overview, below the basemap labels.
    map.addLayer(
      {
        id: LAYER.heat,
        type: 'heatmap',
        source: SRC.heat,
        paint: {
          'heatmap-weight': weightExpression(0) as unknown as ExpressionSpecification,
          'heatmap-intensity': 0.55,
          'heatmap-color': HEAT_COLOR,
          // Radius doubles with each zoom level so the kernel keeps covering ~1.6 grid cells (15 mi spacing).
          'heatmap-radius': [
            'interpolate',
            ['exponential', 2],
            ['zoom'],
            3,
            5,
            10,
            640,
          ] as unknown as ExpressionSpecification,
          'heatmap-opacity': 0.85,
        },
      },
      before,
    );
    map.addLayer(
      {
        id: LAYER.heatUnknown,
        type: 'circle',
        source: SRC.heat,
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            3,
            2.5,
            8,
            5,
          ] as unknown as ExpressionSpecification,
          'circle-color': '#ffffff',
          'circle-opacity': 0,
          'circle-stroke-color': '#7c8591',
          'circle-stroke-width': 1.5,
          'circle-stroke-opacity': 0,
        },
      },
      before,
    );

    // 2. Route lines. Unselected routes keep identity colours; the selected one is risk-coloured below.
    map.addLayer(
      {
        id: LAYER.routeCasing,
        type: 'line',
        source: SRC.routes,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.8 },
      },
      before,
    );
    map.addLayer(
      {
        id: LAYER.routeLine,
        type: 'line',
        source: SRC.routes,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'] as unknown as ExpressionSpecification,
          'line-width': 3.5,
          'line-opacity': [
            'case',
            ['==', ['get', 'selected'], 1],
            0,
            0.85,
          ] as unknown as ExpressionSpecification,
        },
      },
      before,
    );
    map.addLayer(
      {
        id: LAYER.segCasing,
        type: 'line',
        source: SRC.segments,
        layout: { 'line-cap': 'butt', 'line-join': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 9 },
      },
      before,
    );
    map.addLayer(
      {
        id: LAYER.segLine,
        type: 'line',
        source: SRC.segments,
        filter: ['!=', ['get', 'level'], 'unknown'],
        layout: { 'line-cap': 'butt', 'line-join': 'round' },
        paint: { 'line-color': RISK_COLOR, 'line-width': 6 },
      },
      before,
    );
    map.addLayer(
      {
        id: LAYER.segUnknown,
        type: 'line',
        source: SRC.segments,
        filter: ['==', ['get', 'level'], 'unknown'],
        layout: { 'line-cap': 'butt', 'line-join': 'round' },
        paint: { 'line-color': '#7c8591', 'line-width': 5, 'line-dasharray': [1.2, 1.2] },
      },
      before,
    );
    map.addLayer({
      id: LAYER.routeHit,
      type: 'line',
      source: SRC.routes,
      paint: { 'line-color': '#000', 'line-width': 16, 'line-opacity': 0 },
    });

    // 3. Exact checkpoint markers (authoritative), above everything else.
    map.addLayer({
      id: LAYER.cpHalo,
      type: 'circle',
      source: SRC.checkpoints,
      filter: ['==', ['get', 'i'], -1],
      paint: {
        'circle-radius': ['+', ['get', 'radius'], 7] as unknown as ExpressionSpecification,
        'circle-color': 'rgba(255,255,255,0.01)',
        'circle-stroke-color': '#111827',
        'circle-stroke-width': 3,
      },
    });
    map.addLayer({
      id: LAYER.cpCircle,
      type: 'circle',
      source: SRC.checkpoints,
      layout: { 'circle-sort-key': ['get', 'sortKey'] as unknown as ExpressionSpecification },
      paint: {
        'circle-radius': [
          '*',
          ['get', 'radius'],
          ['case', ['==', ['get', 'selected'], 1], 1, 0.72],
        ] as unknown as ExpressionSpecification,
        'circle-color': levelMatch(
          'level',
          (l) => (l === 'unknown' ? '#ffffff' : RISK_STYLES[l].color),
          '#ffffff',
        ),
        'circle-opacity': [
          'case',
          ['==', ['get', 'level'], 'unknown'],
          0.35,
          1,
        ] as unknown as ExpressionSpecification,
        'circle-stroke-color': [
          'case',
          ['==', ['get', 'level'], 'unknown'],
          '#5b6470',
          '#ffffff',
        ] as unknown as ExpressionSpecification,
        'circle-stroke-width': [
          'case',
          ['==', ['get', 'level'], 'unknown'],
          2.5,
          2,
        ] as unknown as ExpressionSpecification,
        'circle-stroke-opacity': [
          'case',
          ['==', ['get', 'selected'], 1],
          1,
          0.8,
        ] as unknown as ExpressionSpecification,
      },
    });
    map.addLayer({
      id: LAYER.cpLetter,
      type: 'symbol',
      source: SRC.checkpoints,
      filter: ['==', ['get', 'selected'], 1],
      layout: {
        'text-field': ['get', 'letter'] as unknown as ExpressionSpecification,
        'text-font': ['Noto Sans Bold'],
        'text-size': 11,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        'symbol-sort-key': ['get', 'sortKey'] as unknown as ExpressionSpecification,
      },
      paint: {
        'text-color': [
          'match',
          ['get', 'level'],
          'moderate',
          '#2a1f00',
          'unknown',
          '#3d4650',
          '#ffffff',
        ] as unknown as ExpressionSpecification,
      },
    });

    map.on('click', LAYER.cpCircle, (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const props = f.properties as { routeId: string; i: number };
      this.callbacks.onCheckpointClick(props.routeId, Number(props.i));
    });
    map.on('click', LAYER.routeHit, (e) => {
      // Checkpoints take precedence over the line underneath them.
      if (map.queryRenderedFeatures(e.point, { layers: [LAYER.cpCircle] }).length > 0) return;
      const f = e.features?.[0];
      if (f) this.callbacks.onRouteClick(String((f.properties as { id: string }).id));
    });
    for (const layer of [LAYER.cpCircle, LAYER.routeHit]) {
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''));
    }
  }

  private setSource(id: string, data: unknown): void {
    (this.map.getSource(id) as GeoJSONSource | undefined)?.setData(data as never);
  }

  // ---- routes -----------------------------------------------------------------------------------

  setRoutes(
    routes: Route[],
    selectedId: string | null,
    recommendedId: string | null,
    departureUtc: string,
    pins: PinSpec[],
    fit: boolean,
  ): void {
    this.routes = routes;
    this.selectedId = selectedId;
    this.recommendedId = recommendedId;
    this.departureUtc = departureUtc;
    this.pinSpecs = pins;
    this.whenReady(() => {
      this.syncRouteSources();
      this.renderChips();
      this.renderPins();
      if (fit) this.fitToRoutes();
    });
  }

  setSelectedRoute(selectedId: string | null): void {
    this.selectedId = selectedId;
    this.whenReady(() => {
      this.syncRouteSources();
      this.renderChips();
    });
  }

  private syncRouteSources(): void {
    const selected = this.routes.find((r) => r.id === this.selectedId);
    this.setSource(SRC.routes, routeLines(this.routes, this.selectedId));
    this.setSource(SRC.segments, selectedSegments(selected));
    this.setSource(SRC.checkpoints, checkpointPoints(this.routes, this.selectedId));
  }

  fitToRoutes(): void {
    const coords = this.routes.flatMap((r) => r.geometry.coordinates);
    const b = boundsOf(coords);
    if (b) this.map.fitBounds(b as LngLatBoundsLike, { padding: 56, duration: 600, maxZoom: 10 });
  }

  private renderPins(): void {
    this.pinMarkers.forEach((m) => m.remove());
    this.pinMarkers = this.pinSpecs.map((p) => {
      const node = document.createElement('div');
      node.className = `map-pin map-pin--${p.kind}`;
      node.setAttribute('role', 'img');
      node.setAttribute('aria-label', `${p.kind === 'start' ? 'Start' : 'End'}: ${p.label}`);
      const dot = document.createElement('span');
      dot.className = 'map-pin__dot';
      dot.textContent = p.kind === 'start' ? 'A' : 'B';
      const text = document.createElement('span');
      text.className = 'map-pin__label';
      text.textContent = p.kind === 'start' ? 'Start' : 'End';
      node.append(dot, text);
      return new this.ml.Marker({ element: node, anchor: 'bottom' }).setLngLat(p.lngLat).addTo(this.map);
    });
  }

  private renderChips(): void {
    this.chipMarkers.forEach((m) => m.remove());
    const fractions = this.routes.length > 1 ? [0.38, 0.5, 0.62, 0.45] : [0.5];
    this.chipMarkers = this.routes.map((r, index) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      const recommended = r.id === this.recommendedId;
      const blocked = r.eligibility.reasons.includes('no_travel');
      btn.className = `route-chip${r.id === this.selectedId ? ' route-chip--selected' : ''}`;
      btn.textContent = `${r.id}${recommended ? ' ★' : ''}${blocked ? ' ⊘' : ''} · ${formatDuration(r.duration_s)} · ${formatMiles(r.distance_mi)}`;
      btn.setAttribute(
        'aria-label',
        `${r.name}${recommended ? ', recommended' : ''}${blocked ? ', has No Travel conditions' : ''}: ${formatDuration(r.duration_s)}, ${formatMiles(r.distance_mi)}. Select route`,
      );
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.callbacks.onRouteClick(r.id);
      });
      const at = pointAlong(r.geometry.coordinates, fractions[index % fractions.length] ?? 0.5);
      return new this.ml.Marker({ element: btn, anchor: 'center' }).setLngLat(at).addTo(this.map);
    });
  }

  // ---- checkpoint popup -------------------------------------------------------------------------

  /** Highlights a checkpoint and opens its popup; `null` clears both. */
  setSelectedCheckpoint(routeId: string | null, index: number | null, flyTo: boolean): void {
    this.whenReady(() => {
      this.map.setFilter(
        LAYER.cpHalo,
        routeId !== null && index !== null
          ? ['all', ['==', ['get', 'routeId'], routeId], ['==', ['get', 'i'], index]]
          : ['==', ['get', 'i'], -1],
      );
      this.closePopup();
      if (routeId === null || index === null) return;
      const route = this.routes.find((r) => r.id === routeId);
      const cp: Checkpoint | undefined = route?.checkpoints.find((c) => c.i === index);
      if (!route || !cp) return;
      // On tall maps open the popup above the marker, and sit the marker below centre so the popup fits
      // above it without running under the slider card.
      const tall = this.map.getContainer().clientHeight > 600;
      this.popup = new this.ml.Popup({
        offset: 16,
        maxWidth: '300px',
        closeButton: true,
        focusAfterOpen: false,
        ...(tall ? { anchor: 'bottom' as const } : {}),
      })
        .setLngLat([cp.lon, cp.lat])
        .setDOMContent(buildCheckpointPopup(route, cp, this.departureUtc))
        .addTo(this.map);
      this.popup.on('close', () => {
        if (!this.suppressPopupClose) this.callbacks.onPopupClose();
      });
      this.map.easeTo({
        center: [cp.lon, cp.lat],
        duration: flyTo ? 500 : 350,
        offset: [0, tall ? 130 : 0],
      });
    });
  }

  private closePopup(): void {
    if (!this.popup) return;
    this.suppressPopupClose = true;
    this.popup.remove();
    this.suppressPopupClose = false;
    this.popup = null;
  }

  // ---- heatmap ----------------------------------------------------------------------------------

  setHeatmap(data: HeatmapData | null): void {
    this.whenReady(() => {
      this.setSource(SRC.heat, data ? toFeatureCollection(data) : empty);
      this.appliedHour = -1;
      this.applyHour(this.pendingHour);
    });
  }

  setHeatVisible(visible: boolean): void {
    this.whenReady(() => {
      const v = visible ? 'visible' : 'none';
      this.map.setLayoutProperty(LAYER.heat, 'visibility', v);
      this.map.setLayoutProperty(LAYER.heatUnknown, 'visibility', v);
    });
  }

  /** Coalesces rapid slider updates into at most one paint-property change per animation frame. */
  setHour(hour: number): void {
    this.pendingHour = hour;
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.whenReady(() => this.applyHour(this.pendingHour));
    });
  }

  private applyHour(hour: number): void {
    if (hour === this.appliedHour || this.destroyed) return;
    this.appliedHour = hour;
    this.map.setPaintProperty(
      LAYER.heat,
      'heatmap-weight',
      weightExpression(hour) as unknown as ExpressionSpecification,
    );
    const unknown = unknownOpacityExpression(hour) as unknown as ExpressionSpecification;
    this.map.setPaintProperty(LAYER.heatUnknown, 'circle-opacity', unknown);
    this.map.setPaintProperty(LAYER.heatUnknown, 'circle-stroke-opacity', unknown);
  }

  // ---- lifecycle --------------------------------------------------------------------------------

  resize(): void {
    this.map.resize();
  }

  destroy(): void {
    this.destroyed = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.closePopup();
    this.chipMarkers.forEach((m) => m.remove());
    this.pinMarkers.forEach((m) => m.remove());
    this.map.remove();
  }
}
