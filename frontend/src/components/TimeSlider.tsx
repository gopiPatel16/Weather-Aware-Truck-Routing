import { useEffect, useState } from 'react';
import { formatHourOffset, formatInZone } from '../utils/format';

export const SLIDER_MAX_HOUR = 48;
/** Autoplay pace: one forecast hour per tick. */
export const PLAY_TICK_MS = 450;

interface Props {
  hour: number;
  startUtc: string;
  /** Origin IANA zone — the label always reads in the origin's local time. */
  timeZone: string;
  onHourChange: (hour: number) => void;
  disabled?: boolean;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

/**
 * 0–48 h slider with ▶ play. It only reports the hour; the heatmap data for every hour is already in memory,
 * so nothing here (or downstream) makes a network request.
 */
export function TimeSlider({ hour, startUtc, timeZone, onHourChange, disabled = false }: Props) {
  const reduced = usePrefersReducedMotion();
  const [playing, setPlaying] = useState(false);
  const stopped = playing && (reduced || disabled);
  useEffect(() => {
    if (!playing || reduced || disabled) return;
    const id = setTimeout(() => {
      if (hour >= SLIDER_MAX_HOUR) setPlaying(false);
      else onHourChange(hour + 1);
    }, PLAY_TICK_MS);
    return () => clearTimeout(id);
  }, [playing, reduced, disabled, hour, onHourChange]);

  const when = new Date(Date.parse(startUtc) + hour * 3_600_000);
  const label = formatInZone(when, timeZone);
  const isPlaying = playing && !stopped;

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => {
          if (!isPlaying && hour >= SLIDER_MAX_HOUR) onHourChange(0);
          setPlaying(!isPlaying);
        }}
        disabled={disabled || reduced}
        aria-label={isPlaying ? 'Pause forecast animation' : 'Play forecast animation'}
        title={reduced ? 'Autoplay is off because your system prefers reduced motion' : undefined}
        className="grid size-9 shrink-0 place-items-center rounded-full bg-brand text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span aria-hidden="true">{isPlaying ? '❚❚' : '▶'}</span>
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2 text-sm">
          <output htmlFor="hour-slider" className="truncate font-semibold" data-testid="slider-label">
            {label}
          </output>
          <span className="shrink-0 text-xs text-muted">{formatHourOffset(hour)}</span>
        </div>
        <input
          id="hour-slider"
          className="hour-slider"
          type="range"
          min={0}
          max={SLIDER_MAX_HOUR}
          step={1}
          value={hour}
          disabled={disabled}
          aria-label="Forecast hour after departure"
          aria-valuetext={`${formatHourOffset(hour)}: ${label} (${timeZone.replace('_', ' ')})`}
          onChange={(e) => onHourChange(Number(e.target.value))}
        />
        <div className="hidden justify-between text-[11px] text-muted lg:flex" aria-hidden="true">
          <span>0 h</span>
          <span>12</span>
          <span>24</span>
          <span>36</span>
          <span>48 h</span>
        </div>
      </div>
    </div>
  );
}
