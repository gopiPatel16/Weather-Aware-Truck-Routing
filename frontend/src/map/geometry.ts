export type LngLat = [number, number];

const toRad = Math.PI / 180;

/** Great-circle distance in metres between two lng/lat points. */
export function distanceM(a: LngLat, b: LngLat): number {
  const dLat = (b[1] - a[1]) * toRad;
  const dLon = (b[0] - a[0]) * toRad;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * toRad) * Math.cos(b[1] * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}

/** Point at `fraction` (0–1) of the path length, by linear interpolation along the vertices. */
export function pointAlong(coords: readonly LngLat[], fraction: number): LngLat {
  const first = coords[0];
  if (!first) throw new Error('pointAlong needs at least one coordinate');
  if (coords.length === 1) return first;
  const lengths: number[] = [];
  let total = 0;
  for (let i = 1; i < coords.length; i++) {
    const d = distanceM(coords[i - 1] as LngLat, coords[i] as LngLat);
    lengths.push(d);
    total += d;
  }
  let target = Math.min(1, Math.max(0, fraction)) * total;
  for (let i = 0; i < lengths.length; i++) {
    const len = lengths[i] ?? 0;
    if (target <= len || i === lengths.length - 1) {
      const t = len === 0 ? 0 : Math.min(1, target / len);
      const a = coords[i] as LngLat;
      const b = coords[i + 1] as LngLat;
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    target -= len;
  }
  return coords[coords.length - 1] as LngLat;
}

export function boundsOf(coords: readonly LngLat[]): [LngLat, LngLat] | null {
  if (coords.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [x, y] of coords) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}
