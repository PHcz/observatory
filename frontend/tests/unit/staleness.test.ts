import { describe, it, expect } from 'vitest';
import { deriveStaleness } from '$lib/utils/staleness';

describe('deriveStaleness', () => {
  it('returns fresh when age < threshold', () => {
    expect(deriveStaleness(50, 100)).toBe('fresh');
  });

  it('returns amber when threshold <= age < threshold * 2.5', () => {
    expect(deriveStaleness(150, 100)).toBe('amber');
    expect(deriveStaleness(100, 100)).toBe('amber');
    expect(deriveStaleness(249, 100)).toBe('amber');
  });

  it('returns red when age >= threshold * 2.5', () => {
    expect(deriveStaleness(300, 100)).toBe('red');
    expect(deriveStaleness(250, 100)).toBe('red');
  });

  it('returns red for invalid inputs', () => {
    expect(deriveStaleness(0, 0)).toBe('red');
    expect(deriveStaleness(50, -1)).toBe('red');
    expect(deriveStaleness(-5, 100)).toBe('red');
    expect(deriveStaleness(Infinity, 100)).toBe('red');
    expect(deriveStaleness(50, Infinity)).toBe('red');
  });
});
