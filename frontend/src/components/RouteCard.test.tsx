import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { estimatedEta, inconclusive, storm } from '../test/fixtures';
import { RouteCard } from './RouteCard';

const baseProps = { index: 0, selected: false, recommended: false, slowerBySeconds: 0, onSelect: vi.fn() };

describe('RouteCard', () => {
  it('shows distance, duration, arrival in the arrival zone, coverage, Severe/High miles, avg risk and ETA method', () => {
    const route = storm().routes[0]!; // Route A, I-80 W
    render(<RouteCard {...baseProps} route={route} />);
    const card = screen.getByRole('button', { name: /Route A/ });
    expect(card).toHaveTextContent('via I-80 W');
    expect(card).toHaveTextContent('920 mi');
    expect(card).toHaveTextContent('14 h 50 min');
    expect(card).toHaveTextContent(/Arrives .*MST/); // Denver zone, not the browser's
    expect(card).toHaveTextContent('100%'); // coverage
    expect(card).toHaveTextContent('75 mi'); // severe
    expect(card).toHaveTextContent('25 mi'); // high
    expect(card).toHaveTextContent('0.35'); // avg risk
    expect(card).toHaveTextContent('ETAs from route travel times');
    expect(card).toHaveTextContent('✓ Eligible');
    expect(within(card).getByRole('img', { name: /Risk along Route A/ })).toBeInTheDocument();
  });

  it('marks the recommended route and shows the slower-than-fastest delta', () => {
    render(<RouteCard {...baseProps} route={storm().routes[2]!} recommended slowerBySeconds={2603} />);
    const card = screen.getByRole('button', { name: /Route C/ });
    expect(card).toHaveTextContent('★ Recommended');
    expect(card).toHaveTextContent('+43 min');
  });

  it('shows "Not eligible" with the No Travel reason, and never "Recommended"', () => {
    render(<RouteCard {...baseProps} route={storm().routes[1]!} />);
    const card = screen.getByRole('button', { name: /Route B/ });
    expect(card).toHaveTextContent('⊘ Not eligible');
    expect(card).toHaveTextContent('No Travel conditions on 25 mi');
    expect(card).not.toHaveTextContent('Recommended');
  });

  it('shows incomplete-weather ineligibility, Unknown miles and reduced coverage', () => {
    render(<RouteCard {...baseProps} route={inconclusive().routes[0]!} />);
    const card = screen.getByRole('button', { name: /Route A/ });
    expect(card).toHaveTextContent('Forecast covers only 53% of the route');
    expect(card).toHaveTextContent('Unknown');
    expect(card).toHaveTextContent('432.3 mi');
  });

  it('flags estimated ETAs', () => {
    render(<RouteCard {...baseProps} route={estimatedEta().routes[0]!} />);
    expect(screen.getByRole('button')).toHaveTextContent('ETAs estimated from average speed');
  });

  it('reports selection state and calls onSelect with the route id', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<RouteCard {...baseProps} route={storm().routes[0]!} selected onSelect={onSelect} />);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    await user.click(btn);
    expect(onSelect).toHaveBeenCalledWith('A');
  });
});
