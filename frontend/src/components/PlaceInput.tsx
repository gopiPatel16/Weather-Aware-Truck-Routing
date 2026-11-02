import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { api } from '../api/client';
import { isAbortError } from '../api/errors';
import type { GeocodeResult } from '../api/types';

export const GEOCODE_DEBOUNCE_MS = 300;
export const GEOCODE_MIN_CHARS = 3;

interface Props {
  label: string;
  text: string;
  selected: GeocodeResult | null;
  error?: string;
  placeholder?: string;
  onTextChange: (text: string) => void;
  onSelect: (place: GeocodeResult) => void;
}

type Status = 'idle' | 'loading' | 'ready' | 'error';

/** Accessible combobox (ARIA 1.2 list autocomplete): debounced geocoding, stale requests aborted, keyboard navigation. */
export function PlaceInput({ label, text, selected, error, placeholder, onTextChange, onSelect }: Props) {
  const uid = useId();
  const inputId = `${uid}-input`;
  const listId = `${uid}-list`;
  const errId = `${uid}-err`;
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const query = text.trim();
  const shouldSearch = !selected && query.length >= GEOCODE_MIN_CHARS;

  useEffect(() => {
    if (!shouldSearch) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setStatus('loading');
      api
        .geocode(query, controller.signal)
        .then((r) => {
          setResults(r.results);
          setStatus('ready');
          setActive(r.results.length > 0 ? 0 : -1);
        })
        .catch((e: unknown) => {
          if (isAbortError(e)) return;
          setResults([]);
          setStatus('error');
        });
    }, GEOCODE_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, shouldSearch]);

  useEffect(() => () => clearTimeout(blurTimer.current), []);

  const showList = open && shouldSearch && status !== 'idle';
  const pick = (place: GeocodeResult) => {
    onSelect(place);
    setOpen(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (results.length === 0 ? -1 : (i + 1) % results.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (results.length === 0 ? -1 : (i <= 0 ? results.length : i) - 1));
    } else if (e.key === 'Enter' && showList && active >= 0 && results[active]) {
      e.preventDefault();
      pick(results[active]);
    } else if (e.key === 'Escape' && open) {
      e.preventDefault();
      setOpen(false);
    }
  };

  let message = '';
  if (shouldSearch && open) {
    if (status === 'loading') message = 'Searching…';
    else if (status === 'error') message = 'Search failed. Keep typing to retry.';
    else if (status === 'ready' && results.length === 0)
      message = 'No match found. Try a nearby city or full address.';
    else if (status === 'ready')
      message = `${results.length} suggestion${results.length === 1 ? '' : 's'} available`;
  }

  return (
    <div className="relative">
      <label htmlFor={inputId} className="mb-1 block text-sm font-semibold">
        {label}
      </label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errId : undefined}
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          onTextChange(e.target.value);
          setOpen(true);
          if (e.target.value.trim().length < GEOCODE_MIN_CHARS) {
            setStatus('idle');
            setResults([]);
          }
        }}
        onFocus={() => {
          clearTimeout(blurTimer.current);
          setOpen(true);
        }}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={onKeyDown}
        className={`w-full rounded-lg border bg-white px-3 py-2 text-sm ${
          error ? 'border-red-700' : selected ? 'border-emerald-700' : 'border-slate-400'
        }`}
      />
      <ul
        id={listId}
        role="listbox"
        aria-label={`${label} suggestions`}
        hidden={!showList || results.length === 0}
        className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-line bg-white py-1 shadow-lg"
      >
        {results.map((r, i) => (
          <li
            key={`${r.label}-${r.lat}`}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={i === active}
            onMouseDown={(e) => {
              e.preventDefault();
              pick(r);
            }}
            onMouseEnter={() => setActive(i)}
            className={`cursor-pointer px-3 py-2 text-sm ${i === active ? 'bg-sky-100' : ''}`}
          >
            {r.label}
            <span className="ml-2 text-xs text-muted">{r.timezone}</span>
          </li>
        ))}
      </ul>
      <p
        aria-live="polite"
        className={message && results.length === 0 ? 'mt-1 text-xs text-muted' : 'sr-only-live'}
      >
        {message}
      </p>
      {error ? (
        <p id={errId} className="mt-1 text-xs font-medium text-red-800">
          {error}
        </p>
      ) : null}
    </div>
  );
}
