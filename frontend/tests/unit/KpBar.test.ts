import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import KpBar from '$lib/atoms/KpBar.svelte';

describe('KpBar', () => {
  it('renders 2 active-low cells when kpIndex=2', () => {
    const { container } = render(KpBar, { props: { kpIndex: 2 } });
    const cells = container.querySelectorAll('.kp-cell');
    const activeLow = container.querySelectorAll('.active-low');
    const activeMid = container.querySelectorAll('.active-mid');
    const activeHigh = container.querySelectorAll('.active-high');
    expect(cells.length).toBe(9);
    expect(activeLow.length).toBe(2);
    expect(activeMid.length).toBe(0);
    expect(activeHigh.length).toBe(0);
  });

  it('renders 5 active-mid cells when kpIndex=5', () => {
    const { container } = render(KpBar, { props: { kpIndex: 5 } });
    const activeMid = container.querySelectorAll('.active-mid');
    const activeLow = container.querySelectorAll('.active-low');
    const activeHigh = container.querySelectorAll('.active-high');
    expect(activeMid.length).toBe(5);
    expect(activeLow.length).toBe(0);
    expect(activeHigh.length).toBe(0);
  });

  it('renders 7 active-high cells when kpIndex=7', () => {
    const { container } = render(KpBar, { props: { kpIndex: 7 } });
    const activeHigh = container.querySelectorAll('.active-high');
    const activeLow = container.querySelectorAll('.active-low');
    const activeMid = container.querySelectorAll('.active-mid');
    expect(activeHigh.length).toBe(7);
    expect(activeLow.length).toBe(0);
    expect(activeMid.length).toBe(0);
  });

  it('renders 0 active cells when kpIndex=null', () => {
    const { container } = render(KpBar, { props: { kpIndex: null } });
    const activeLow = container.querySelectorAll('.active-low');
    const activeMid = container.querySelectorAll('.active-mid');
    const activeHigh = container.querySelectorAll('.active-high');
    expect(activeLow.length).toBe(0);
    expect(activeMid.length).toBe(0);
    expect(activeHigh.length).toBe(0);
  });
});
