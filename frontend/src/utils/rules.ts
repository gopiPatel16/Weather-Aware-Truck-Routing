/** The risk rule tables exactly as in PLAN §5.6, for the Rules drawer. */
export const RULE_BANDS = [
  { level: 'low', wind: 'x < 25', rain: 'x < 0.10', snow: 'x < 0.5' },
  { level: 'moderate', wind: '25 ≤ x < 35', rain: '0.10 ≤ x < 0.25', snow: '0.5 ≤ x < 1.0' },
  { level: 'high', wind: '35 ≤ x < 45', rain: '0.25 ≤ x < 0.50', snow: '1.0 ≤ x < 2.0' },
  { level: 'severe', wind: '45 ≤ x < 55', rain: '0.50 ≤ x ≤ 1.00', snow: '2.0 ≤ x ≤ 3.0' },
  { level: 'no_travel', wind: 'x ≥ 55', rain: 'x > 1.00', snow: 'x > 3.0' },
] as const;

/** Cargo-weight load rules (strictly "greater than"), applied as a floor under the weather level. */
export const LOAD_RULES = [
  { when: 'Wind ≥ 55 mph', cargo: 'any load', result: 'no_travel' },
  { when: '45 ≤ wind < 55 mph', cargo: 'cargo > 30,000 lb', result: 'no_travel' },
  { when: '35 ≤ wind < 45 mph', cargo: 'cargo > 40,000 lb', result: 'severe' },
] as const;

export const LOAD_THRESHOLD_HELP =
  'Load rules: above 30,000 lb, 45–54 mph wind is No Travel; above 40,000 lb, 35–44 mph wind is Severe.';
