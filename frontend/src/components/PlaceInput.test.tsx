import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CHICAGO, jsonResponse } from '../test/fixtures';
import { useState } from 'react';
import type { GeocodeResult } from '../api/types';
import { PlaceInput } from './PlaceInput';

function Harness({ onPick }: { onPick?: (p: GeocodeResult) => void }) {
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<GeocodeResult | null>(null);
  return (
    <PlaceInput
      label="Origin"
      text={text}
      selected={selected}
      onTextChange={(t) => {
        setText(t);
        setSelected(null);
      }}
      onSelect={(p) => {
        setSelected(p);
        setText(p.label);
        onPick?.(p);
      }}
    />
  );
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => jsonResponse({ results: [CHICAGO] }));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const type = (value: string) => fireEvent.change(screen.getByRole('combobox'), { target: { value } });

describe('PlaceInput combobox', () => {
  it('waits 300 ms of silence and needs 3 characters before searching', async () => {
    render(<Harness />);
    type('Ch');
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(fetchMock).not.toHaveBeenCalled();

    type('Chi');
    await act(() => vi.advanceTimersByTimeAsync(299));
    expect(fetchMock).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toBe('/api/geocode?q=Chi');
  });

  it('debounces rapid typing into a single request', async () => {
    render(<Harness />);
    type('Chi');
    await act(() => vi.advanceTimersByTimeAsync(200));
    type('Chic');
    await act(() => vi.advanceTimersByTimeAsync(200));
    type('Chica');
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toBe('/api/geocode?q=Chica');
  });

  it('aborts a stale in-flight request when the text changes', async () => {
    const signals: AbortSignal[] = [];
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      signals.push(init.signal as AbortSignal);
      return new Promise(() => undefined);
    });
    render(<Harness />);
    type('Chi');
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(signals[0]!.aborted).toBe(false);
    type('Chic');
    expect(signals[0]!.aborted).toBe(true);
  });

  it('supports keyboard selection (ArrowDown / Enter) and exposes combobox semantics', async () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);
    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('aria-autocomplete', 'list');
    type('Chi');
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(input).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('option', { name: /Chicago/ })).toBeInTheDocument();
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', expect.stringMatching(/-0$/));
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onPick).toHaveBeenCalledWith(CHICAGO);
    expect(input).toHaveValue('Chicago, IL, USA');
  });

  it('says so when nothing matches', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ results: [] }));
    render(<Harness />);
    type('Zzzz');
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(screen.getByText(/no match found/i)).toBeInTheDocument();
  });
});
