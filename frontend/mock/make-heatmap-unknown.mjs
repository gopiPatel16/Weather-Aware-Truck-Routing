// Derives mock/fixtures/heatmap_unknown.json from heatmap_storm.json: far-west cells have no forecast at all (all '9'),
// and every cell loses its last hours (beyond the forecast horizon). Run: node mock/make-heatmap-unknown.mjs
import { readFileSync, writeFileSync } from 'node:fs';

const src = JSON.parse(readFileSync(new URL('./fixtures/heatmap_storm.json', import.meta.url), 'utf8'));
let unknownCells = 0;
src.cells = src.cells.map((cell) => {
  const noForecast = cell.lon < -99;
  if (noForecast) unknownCells += 1;
  const levels = noForecast ? '9'.repeat(49) : cell.levels.slice(0, 44) + '99999';
  return { ...cell, levels };
});
src.meta = {
  ...src.meta,
  unknown_cells: unknownCells,
  warnings: ['Forecast unavailable west of 99°W (mock).'],
};
writeFileSync(new URL('./fixtures/heatmap_unknown.json', import.meta.url), JSON.stringify(src));
console.log(`cells=${src.cells.length} unknown=${unknownCells}`);
