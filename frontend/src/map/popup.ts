import type { Checkpoint, Route } from '../api/types';
import { formatInHr, formatInZone, formatMiles, formatMph, formatTempF } from '../utils/format';
import { forecastBasisText } from '../utils/forecast';
import { RISK_STYLES } from '../utils/risk';

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Popup body for a checkpoint. Built with DOM nodes (no HTML strings) so provider text can never inject markup. */
export function buildCheckpointPopup(route: Route, cp: Checkpoint, departureUtc: string): HTMLElement {
  const style = RISK_STYLES[cp.risk.level];
  const root = el('div', 'cp-popup');

  const title = el('div', 'cp-popup__title');
  title.append(el('strong', undefined, `${route.name} · mile ${formatMiles(cp.mile)}`));
  root.append(title);

  const badge = el('div', 'cp-popup__badge', `${style.icon} ${style.label}`);
  badge.style.background = style.bg;
  badge.style.color = style.fg;
  root.append(badge);

  if (cp.risk.level === 'unknown') {
    root.append(
      el(
        'p',
        'cp-popup__note',
        cp.risk.missing.length
          ? `Forecast missing: ${cp.risk.missing.join(', ')}. Unknown is never treated as Low.`
          : 'No forecast available. Unknown is never treated as Low.',
      ),
    );
  }

  root.append(
    el('div', 'cp-popup__eta', `ETA ${formatInZone(cp.eta_utc, cp.tz)}`),
    el('div', 'cp-popup__muted', cp.tz.replace('_', ' ')),
  );
  const hoursIn = (Date.parse(cp.eta_utc) - Date.parse(departureUtc)) / 3_600_000;
  if (Number.isFinite(hoursIn))
    root.append(el('div', 'cp-popup__muted', `${hoursIn.toFixed(1)} h after departure`));

  if (cp.weather) {
    const w = cp.weather;
    const list = el('dl', 'cp-popup__values');
    const rows: [string, string][] = [
      ['Wind', formatMph(w.wind_mph)],
      ['Gusts (info only)', formatMph(w.gust_mph)],
      ['Rain', formatInHr(w.rain_in_hr)],
      ['Snow', formatInHr(w.snow_in_hr)],
      ['Temperature', formatTempF(w.temp_f)],
    ];
    for (const [k, v] of rows) {
      list.append(el('dt', undefined, k), el('dd', undefined, v));
    }
    root.append(list);
  }

  if (cp.risk.drivers.length > 0) {
    root.append(el('div', 'cp-popup__h', 'Why this level'));
    const ul = el('ul', 'cp-popup__drivers');
    for (const d of cp.risk.drivers) {
      const li = el('li', undefined, d.text);
      if (d.factor === 'load_rule') li.className = 'cp-popup__load';
      ul.append(li);
    }
    root.append(ul);
  }

  root.append(el('div', 'cp-popup__h', 'Forecast hours used'));
  const basis = el('ul', 'cp-popup__basis');
  for (const line of forecastBasisText(cp)) basis.append(el('li', undefined, line));
  root.append(basis);
  return root;
}
