import { useEffect, useState } from 'react';
import { getScenario, setScenario, subscribeScenario } from './install';
import { SCENARIO_IDS, SCENARIO_LABELS, type ScenarioId } from './scenarios';

/** Header control (mock mode only) that chooses which fixture scenario the fake API answers with. */
export function MockScenarioPicker() {
  const [id, setId] = useState<ScenarioId>(getScenario());
  useEffect(() => subscribeScenario(setId), []);
  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span className="rounded bg-amber-300 px-1.5 py-0.5 font-bold text-amber-950">MOCK</span>
      <span className="sr-only">Mock scenario</span>
      <select
        value={id}
        onChange={(e) => setScenario(e.target.value as ScenarioId)}
        className="max-w-[11rem] rounded-md border border-white/40 bg-brand-dark px-1.5 py-1 text-white lg:max-w-xs"
      >
        {SCENARIO_IDS.map((s) => (
          <option key={s} value={s}>
            {SCENARIO_LABELS[s]}
          </option>
        ))}
      </select>
    </label>
  );
}
