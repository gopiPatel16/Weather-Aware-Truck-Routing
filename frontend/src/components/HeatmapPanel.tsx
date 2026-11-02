import type { HeatmapState } from '../state/useHeatmap';
import { TimeSlider } from './TimeSlider';

interface Props {
  state: HeatmapState;
  hour: number;
  startUtc: string;
  originTimeZone: string;
  heatVisible: boolean;
  onHourChange: (hour: number) => void;
  onHeatVisibleChange: (visible: boolean) => void;
  onRetry: () => void;
}

/** Slider card over the map: loading / failed / ready states. A failure never blocks the routes. */
export function HeatmapPanel({
  state,
  hour,
  startUtc,
  originTimeZone,
  heatVisible,
  onHourChange,
  onHeatVisibleChange,
  onRetry,
}: Props) {
  return (
    <section
      aria-label="Forecast heatmap"
      className="pointer-events-auto w-full max-w-xl rounded-xl border border-line bg-white/95 p-2 shadow-lg lg:p-3 backdrop-blur"
    >
      {state.phase === 'error' ? (
        <div role="status" className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>
            <span aria-hidden="true">⚠ </span>
            Forecast overview unavailable ({state.message}). Routes and checkpoints are unaffected.
          </span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-slate-500 px-2.5 py-1 text-xs font-semibold hover:bg-slate-100"
          >
            Retry heatmap
          </button>
        </div>
      ) : (
        <>
          <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
            <span className="font-semibold">
              {state.phase === 'loading'
                ? 'Loading forecast overview…'
                : 'Smoothed forecast overview at slider time'}
            </span>
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={heatVisible}
                onChange={(e) => onHeatVisibleChange(e.target.checked)}
                disabled={state.phase !== 'ready'}
              />
              Show heat layer
            </label>
          </div>
          <TimeSlider
            hour={hour}
            startUtc={startUtc}
            timeZone={originTimeZone}
            onHourChange={onHourChange}
            disabled={state.phase !== 'ready'}
          />
          {state.phase === 'ready' && state.data.warnings.length > 0 ? (
            <p className="mt-1 text-xs text-amber-900">⚠ {state.data.warnings.join(' ')}</p>
          ) : null}
        </>
      )}
    </section>
  );
}
