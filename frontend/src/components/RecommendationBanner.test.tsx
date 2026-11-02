import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { estimatedEta, inconclusive, noSafeRoute, storm, twoRoutes } from '../test/fixtures';
import { PlanNotices } from './PlanNotices';
import { RecommendationBanner } from './RecommendationBanner';

describe('RecommendationBanner', () => {
  it('recommended: shows the headline, reasons and caveats', () => {
    render(<RecommendationBanner plan={storm()} />);
    const region = screen.getByRole('region', { name: /Route C is the safest eligible route/ });
    expect(region).toHaveAttribute('data-status', 'recommended');
    expect(within(region).getByText(/Fewer Severe miles: 50 vs 75 on Route A/)).toBeInTheDocument();
    expect(within(region).getByText(/Still includes 50 mi of Severe risk/)).toBeInTheDocument();
  });

  it('no_safe_route: says "No safe route available" and recommends nothing', () => {
    render(<RecommendationBanner plan={noSafeRoute()} />);
    expect(screen.getByRole('heading', { name: /No safe route available/ })).toBeInTheDocument();
    expect(screen.getByText(/none is recommended/i)).toBeInTheDocument();
    expect(screen.queryByText(/recommended$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/safest eligible/i)).not.toBeInTheDocument();
    expect(screen.getByRole('region')).toHaveAttribute('data-status', 'no_safe_route');
  });

  it('inconclusive: says a safe recommendation cannot be determined and lists coverage per route', () => {
    render(<RecommendationBanner plan={inconclusive()} />);
    expect(
      screen.getByRole('heading', { name: 'A safe recommendation cannot be determined' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Route A: forecast covers 53% of the route/)).toBeInTheDocument();
    expect(screen.getByText(/Route C: forecast covers 55.7% of the route/)).toBeInTheDocument();
    expect(screen.getByText(/never treated as Low/i)).toBeInTheDocument();
  });
});

describe('PlanNotices', () => {
  it('shows the honest alternatives message, highlighted when fewer than 3 routes came back', () => {
    render(<PlanNotices plan={twoRoutes()} />);
    const note = screen.getByTestId('alternatives-message');
    expect(note).toHaveTextContent('The routing provider returned 2 valid alternatives for this trip.');
    expect(note).toHaveAttribute('data-limited', 'true');
  });

  it('does not flag the message when all three routes were returned', () => {
    render(<PlanNotices plan={storm()} />);
    expect(screen.getByTestId('alternatives-message')).toHaveAttribute('data-limited', 'false');
  });

  it('flags estimated ETAs once instead of repeating every per-route warning', () => {
    render(<PlanNotices plan={estimatedEta()} />);
    expect(screen.getAllByText(/estimated from average speed/i)).toHaveLength(1);
  });

  it('lists backend warnings such as partial forecast coverage', () => {
    render(<PlanNotices plan={inconclusive()} />);
    expect(screen.getByText(/Route A: weather forecast covers only 53.0%/)).toBeInTheDocument();
  });
});
