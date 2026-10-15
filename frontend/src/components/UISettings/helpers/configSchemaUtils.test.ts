import { describe, expect, it } from 'vitest';
import { convertTimeperiodToMilliseconds } from './configSchemaUtils';

describe('convertTimeperiodToMilliseconds', () => {
  // Every unit TimePeriod.__str__ writes, as GET /api/config now serves it.
  it.each([
    ['2500us', 2.5],
    ['120ms', 120],
    ['30s', 30_000],
    ['1min', 60_000],
    ['2h', 7_200_000],
    ['1d', 86_400_000],
    ['30', 30],
  ])('reads %s', (value, ms) => {
    expect(convertTimeperiodToMilliseconds(value)).toBe(ms);
  });
});
