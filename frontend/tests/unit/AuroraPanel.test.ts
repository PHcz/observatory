import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { auroraStore } from '$lib/stores/aurora';
import AuroraPanel from '$lib/panels/AuroraPanel.svelte';

describe('AuroraPanel', () => {
  beforeEach(() => {
    auroraStore.set({ current: null, lastUpdateTs: null });
  });

  it('shows empty state when current is null', () => {
    render(AuroraPanel);
    expect(screen.getByText('No aurora data yet.')).toBeTruthy();
  });

  it('shows section title "AURORA VISIBILITY"', () => {
    render(AuroraPanel);
    expect(screen.getByText('AURORA VISIBILITY')).toBeTruthy();
  });

  it('shows red copy and status-red dot for status=red', () => {
    auroraStore.set({ current: { ts: 1000, status: 'red', detail: null }, lastUpdateTs: 1000 });
    const { container } = render(AuroraPanel);
    expect(screen.getByText('Red · Aurora likely tonight')).toBeTruthy();
    const dot = container.querySelector('.status-red');
    expect(dot).toBeTruthy();
  });

  it('shows green copy for status=green', () => {
    auroraStore.set({ current: { ts: 1000, status: 'green', detail: null }, lastUpdateTs: 1000 });
    render(AuroraPanel);
    expect(screen.getByText('Green · No significant activity')).toBeTruthy();
  });

  it('shows yellow copy for status=yellow', () => {
    auroraStore.set({ current: { ts: 1000, status: 'yellow', detail: null }, lastUpdateTs: 1000 });
    render(AuroraPanel);
    expect(screen.getByText('Yellow · Minor activity possible')).toBeTruthy();
  });

  it('shows amber copy for status=amber', () => {
    auroraStore.set({ current: { ts: 1000, status: 'amber', detail: null }, lastUpdateTs: 1000 });
    render(AuroraPanel);
    expect(screen.getByText('Amber · Aurora possible tonight')).toBeTruthy();
  });

  it('renders detail text when present', () => {
    auroraStore.set({ current: { ts: 1000, status: 'red', detail: 'Some detail' }, lastUpdateTs: 1000 });
    render(AuroraPanel);
    expect(screen.getByText('Some detail')).toBeTruthy();
  });

  it('dot has class containing green for status=green (legacy)', () => {
    auroraStore.set({ current: { ts: 1000, status: 'green', detail: null }, lastUpdateTs: 1000 });
    const { container } = render(AuroraPanel);
    const dot = container.querySelector('[class*="green"]');
    expect(dot).toBeTruthy();
  });

  it('dot has class containing red for status=red (legacy)', () => {
    auroraStore.set({ current: { ts: 1000, status: 'red', detail: null }, lastUpdateTs: 1000 });
    const { container } = render(AuroraPanel);
    const dot = container.querySelector('[class*="red"]');
    expect(dot).toBeTruthy();
  });
});
