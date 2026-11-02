import { RISK_ORDER, RISK_STYLES } from '../utils/risk';

export const LEGEND_NOTE =
  'Markers and route colours show exact categories at your ETA; the heat layer is smoothed.';

export function Legend() {
  return (
    <div className="text-xs">
      <ul className="grid grid-cols-3 gap-x-3 gap-y-1">
        {RISK_ORDER.map((level) => {
          const s = RISK_STYLES[level];
          return (
            <li key={level} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="grid size-4 place-items-center rounded-full text-[9px] font-bold leading-none"
                style={
                  level === 'unknown'
                    ? { border: '2px solid #5b6470', background: '#fff', color: '#3d4650' }
                    : {
                        background: s.color,
                        color: level === 'moderate' ? '#2a1f00' : '#fff',
                        border: '1.5px solid #fff',
                        boxShadow: '0 0 0 1px #94a3b8',
                      }
                }
              >
                {s.letter}
              </span>
              <span>{s.label}</span>
            </li>
          );
        })}
      </ul>
      <p className="mt-1.5 text-muted">{LEGEND_NOTE}</p>
    </div>
  );
}
