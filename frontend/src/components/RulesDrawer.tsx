import { useEffect, useRef } from 'react';
import { LOAD_RULES, RULE_BANDS } from '../utils/rules';
import { RiskBadge } from './RiskBadge';

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Slide-in drawer (native <dialog>: focus trap, Esc to close) with the exact risk rule tables. */
export function RulesDrawer({ open, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      if (typeof dlg.showModal === 'function') dlg.showModal();
      else dlg.setAttribute('open', '');
    } else if (!open && dlg.open) {
      if (typeof dlg.close === 'function') dlg.close();
      else dlg.removeAttribute('open');
    }
  }, [open]);

  const th = 'px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-muted';
  const td = 'px-2 py-1.5 tabular-nums';
  return (
    <dialog
      ref={ref}
      className="drawer"
      aria-labelledby="rules-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="flex h-full flex-col">
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 id="rules-title" className="text-lg font-bold">
            Risk rules
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-3 py-1 text-sm font-medium hover:bg-slate-100"
          >
            Close
          </button>
        </header>
        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4 text-sm">
          <section>
            <h3 className="mb-1 font-bold">Weather thresholds</h3>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full border-collapse">
                <caption className="sr-only">Risk level by wind, rain and snow rate</caption>
                <thead className="bg-slate-100">
                  <tr>
                    <th scope="col" className={th}>
                      Level
                    </th>
                    <th scope="col" className={th}>
                      Wind (mph)
                    </th>
                    <th scope="col" className={th}>
                      Rain (in/hr)
                    </th>
                    <th scope="col" className={th}>
                      Snow (in/hr)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {RULE_BANDS.map((b) => (
                    <tr key={b.level} className="border-t border-line">
                      <th scope="row" className="px-2 py-1.5 text-left">
                        <RiskBadge level={b.level} />
                      </th>
                      <td className={td}>{b.wind}</td>
                      <td className={td}>{b.rain}</td>
                      <td className={td}>{b.snow}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-muted">
              Every band includes its lower bound and excludes its upper bound. For rain and snow, No Travel
              starts strictly above the Severe upper bound, so exactly 1.00 in/hr rain and 3.0 in/hr snow are
              Severe. Wind No Travel is 55 mph and above. The highest level among wind, rain, snow and the
              load rules applies.
            </p>
          </section>

          <section>
            <h3 className="mb-1 font-bold">Cargo-weight load rules</h3>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full border-collapse">
                <caption className="sr-only">Minimum risk level by wind and cargo weight</caption>
                <thead className="bg-slate-100">
                  <tr>
                    <th scope="col" className={th}>
                      Wind
                    </th>
                    <th scope="col" className={th}>
                      Cargo
                    </th>
                    <th scope="col" className={th}>
                      Risk is at least
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {LOAD_RULES.map((r) => (
                    <tr key={r.when} className="border-t border-line">
                      <td className={td}>{r.when}</td>
                      <td className={td}>{r.cargo}</td>
                      <td className={td}>
                        <RiskBadge level={r.result} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-muted">
              Load rules only ever raise the level; they never lower it. Cargo weight is used for these rules
              only — it is not sent to the routing provider.
            </p>
          </section>

          <section>
            <h3 className="mb-1 font-bold">Unknown weather</h3>
            <p className="text-muted">
              If a forecast value is missing the checkpoint is <strong>Unknown</strong> — never Low. If the
              known values already reach No Travel, it is No Travel. Unknown is shown as a hollow grey marker
              and a dashed grey route stretch.
            </p>
          </section>

          <section>
            <h3 className="mb-1 font-bold">Which route is recommended</h3>
            <ol className="list-decimal space-y-1 pl-5 text-muted">
              <li>A route with any No Travel miles is not eligible.</li>
              <li>A route needs 100 % weather coverage to be eligible; otherwise it is not eligible.</li>
              <li>
                Eligible routes are ranked by Severe miles, then High miles, then average risk, then travel
                time.
              </li>
              <li>
                If every route has No Travel miles: <strong>No safe route available</strong>. If no route is
                eligible because the forecast is incomplete:{' '}
                <strong>A safe recommendation cannot be determined</strong>.
              </li>
            </ol>
          </section>

          <section>
            <h3 className="mb-1 font-bold">Forecast timing</h3>
            <p className="text-muted">
              Each checkpoint uses the forecast hour that covers its ETA. Rain and snow are totals for the
              preceding hour; wind is interpolated between the two surrounding hours. Within 15 minutes of an
              hour edge the neighbouring hour is also checked and the worse result is kept.
            </p>
          </section>
        </div>
      </div>
    </dialog>
  );
}
