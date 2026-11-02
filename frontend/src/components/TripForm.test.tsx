import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CHICAGO, DENVER } from '../test/fixtures';
import { TripForm } from './TripForm';

describe('TripForm', () => {
  it('has labelled inputs and shows the load-rule thresholds as helper text', () => {
    render(<TripForm busy={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole('combobox', { name: 'Origin' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Destination' })).toBeInTheDocument();
    expect(screen.getByLabelText(/Departure \(local time at origin\)/)).toBeInTheDocument();
    const cargo = screen.getByLabelText('Cargo/load weight (lb)');
    expect(cargo).toHaveAccessibleDescription(/30,000 lb.*No Travel.*40,000 lb.*Severe/);
    expect(screen.getByRole('radio', { name: '10 mi' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '25 mi' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '50 mi' })).toBeInTheDocument();
  });

  it('asks for an origin before it can show the time zone', () => {
    render(<TripForm busy={false} onSubmit={vi.fn()} />);
    expect(screen.getByTestId('origin-zone')).toHaveTextContent(/choose an origin/i);
  });

  it('shows the zone name and abbreviation for a prefilled origin', () => {
    render(<TripForm busy={false} onSubmit={vi.fn()} initial={{ origin: CHICAGO, destination: DENVER }} />);
    expect(screen.getByTestId('origin-zone')).toHaveTextContent(/America\/Chicago · C[SD]T/);
  });

  it('validates on submit and does not call onSubmit while invalid', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<TripForm busy={false} onSubmit={onSubmit} />);
    await user.click(screen.getByRole('button', { name: 'Find safest route' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/fix 3 fields/i);
    expect(screen.getByText(/enter an origin/i)).toBeInTheDocument();
    expect(screen.getByText(/enter a destination/i)).toBeInTheDocument();
    expect(screen.getByText(/enter the cargo weight/i)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Origin' })).toBeInvalid();
  });

  it('rejects cargo weights outside (0, 150 000] lb', async () => {
    const user = userEvent.setup();
    render(<TripForm busy={false} onSubmit={vi.fn()} initial={{ origin: CHICAGO, destination: DENVER }} />);
    const cargo = screen.getByLabelText('Cargo/load weight (lb)');
    await user.type(cargo, '200000');
    await user.click(screen.getByRole('button', { name: 'Find safest route' }));
    expect(screen.getByText(/150,000 lb or less/)).toBeInTheDocument();
  });

  it('submits the naive departure time, weight and interval — no browser time zone, no vehicle spec', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<TripForm busy={false} onSubmit={onSubmit} initial={{ origin: CHICAGO, destination: DENVER }} />);
    await user.type(screen.getByLabelText('Cargo/load weight (lb)'), '42,000');
    await user.click(screen.getByRole('radio', { name: '50 mi' }));
    await user.click(screen.getByRole('button', { name: 'Find safest route' }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const req = onSubmit.mock.calls[0]![0];
    expect(req).toMatchObject({
      origin: { label: 'Chicago, IL, USA', lat: 41.8781, lon: -87.6298 },
      destination: { label: 'Denver, CO, USA', lat: 39.7392, lon: -104.9903 },
      cargo_weight_lb: 42000,
      interval_miles: 50,
    });
    expect(req.departure_local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(Object.keys(req).sort()).toEqual(
      ['cargo_weight_lb', 'departure_local', 'destination', 'interval_miles', 'origin'].sort(),
    );
    expect(req.origin).not.toHaveProperty('timezone');
  });

  it('disables the button while a plan is in flight', () => {
    render(<TripForm busy onSubmit={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Planning…' })).toBeDisabled();
  });
});
