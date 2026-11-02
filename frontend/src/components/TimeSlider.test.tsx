import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { PLAY_TICK_MS, TimeSlider } from './TimeSlider';

const START = '2026-11-02T12:00:00Z'; // 06:00 CST in Chicago

function Harness({ onHour }: { onHour?: (h: number) => void }) {
  const [hour, setHour] = useState(0);
  return (
    <TimeSlider
      hour={hour}
      startUtc={START}
      timeZone="America/Chicago"
      onHourChange={(h) => {
        setHour(h);
        onHour?.(h);
      }}
    />
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('TimeSlider', () => {
  it('spans 0–48 h and labels the time in the ORIGIN zone', () => {
    render(<Harness />);
    const slider = screen.getByRole('slider', { name: /forecast hour/i });
    expect(slider).toHaveAttribute('min', '0');
    expect(slider).toHaveAttribute('max', '48');
    expect(screen.getByTestId('slider-label')).toHaveTextContent('Mon, Nov 2, 6:00 AM CST');
    fireEvent.change(slider, { target: { value: '30' } });
    expect(screen.getByTestId('slider-label')).toHaveTextContent('Tue, Nov 3, 12:00 PM CST');
    expect(slider).toHaveAttribute('aria-valuetext', expect.stringContaining('+30 h'));
  });

  it('is a native range input that can be focused from the keyboard', () => {
    render(<Harness />);
    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('type', 'range');
    expect(slider).toHaveAttribute('step', '1');
    slider.focus();
    expect(slider).toHaveFocus();
  });

  it('makes no network request while scrubbing', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    render(<Harness />);
    const slider = screen.getByRole('slider');
    for (let h = 0; h <= 48; h++) fireEvent.change(slider, { target: { value: String(h) } });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('plays one hour per tick and stops at 48 h', async () => {
    vi.useFakeTimers();
    const onHour = vi.fn();
    render(<Harness onHour={onHour} />);
    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    for (let i = 0; i < 3; i++) await act(() => vi.advanceTimersByTimeAsync(PLAY_TICK_MS));
    expect(onHour.mock.calls.map((c) => c[0])).toEqual([1, 2, 3]);
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
    for (let i = 0; i < 50; i++) await act(() => vi.advanceTimersByTimeAsync(PLAY_TICK_MS));
    expect(onHour).toHaveBeenLastCalledWith(48);
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
  });

  it('respects prefers-reduced-motion by disabling autoplay', () => {
    vi.stubGlobal(
      'matchMedia',
      (q: string) =>
        ({
          matches: q.includes('reduce'),
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        }) as unknown as MediaQueryList,
    );
    render(<Harness />);
    const play = screen.getByRole('button', { name: /play/i });
    expect(play).toBeDisabled();
    expect(play).toHaveAttribute('title', expect.stringMatching(/reduced motion/i));
  });
});
