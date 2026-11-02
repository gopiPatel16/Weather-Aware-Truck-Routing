import { describe, expect, it } from 'vitest';
import { boundsOf, pointAlong, type LngLat } from './geometry';

describe('pointAlong', () => {
  const line: LngLat[] = [
    [0, 0],
    [0, 1],
    [0, 3],
  ];
  it('interpolates by path length, not by vertex count', () => {
    expect(pointAlong(line, 0)).toEqual([0, 0]);
    expect(pointAlong(line, 1)).toEqual([0, 3]);
    const mid = pointAlong(line, 0.5);
    expect(mid[0]).toBeCloseTo(0, 6);
    expect(mid[1]).toBeCloseTo(1.5, 1);
  });

  it('clamps out-of-range fractions and handles a single point', () => {
    expect(pointAlong(line, -1)).toEqual([0, 0]);
    expect(pointAlong(line, 2)).toEqual([0, 3]);
    expect(pointAlong([[5, 6]], 0.5)).toEqual([5, 6]);
  });
});

describe('boundsOf', () => {
  it('returns the south-west and north-east corners', () => {
    expect(
      boundsOf([
        [-87, 41],
        [-105, 39],
        [-95, 42],
      ]),
    ).toEqual([
      [-105, 39],
      [-87, 42],
    ]);
    expect(boundsOf([])).toBeNull();
  });
});
