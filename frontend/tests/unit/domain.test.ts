import { describe, it, expect } from 'vitest';
import { paddedYDomain } from '$lib/charts/domain';

describe('paddedYDomain', () => {
  it('returns null for empty array', () => {
    expect(paddedYDomain([])).toBeNull();
  });
  it('pads positive range by 5%', () => {
    expect(paddedYDomain([0, 10])).toEqual([-1, 11]);
  });
  it('preserves negative range', () => {
    expect(paddedYDomain([-5, 5])).toEqual([-6, 6]);
  });
  it('handles flat series via range guard', () => {
    expect(paddedYDomain([7, 7, 7])).toEqual([6, 8]);
  });
});
