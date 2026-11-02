import type { RiskLevel } from '../api/types';
import { RISK_STYLES } from '../utils/risk';

interface Props {
  level: RiskLevel;
  /** e.g. "At least High" for Unknown checkpoints with a known floor. */
  suffix?: string;
  className?: string;
}

/** Risk is always text + glyph + colour, never colour alone. */
export function RiskBadge({ level, suffix, className = '' }: Props) {
  const s = RISK_STYLES[level];
  return (
    <span
      data-level={level}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-semibold ${className}`}
      style={{ background: s.bg, color: s.fg, border: `1px solid ${s.color}` }}
    >
      <span aria-hidden="true">{s.icon}</span>
      {s.label}
      {suffix ? <span className="font-normal"> · {suffix}</span> : null}
    </span>
  );
}
