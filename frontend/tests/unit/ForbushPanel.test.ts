import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
// RED until Wave 5 (plan 13-05): the panel + forbush store do not exist yet.
import ForbushPanel from '$lib/panels/ForbushPanel.svelte';
import { setForbush } from '$lib/stores/forbush';
import { settingsStore } from '$lib/stores/settings';

beforeEach(() => {
  settingsStore.resetToDefaults();
});

describe('ForbushPanel (RED until Wave 5)', () => {
  it('shows the FORBUSH INDICATOR section title', () => {
    render(ForbushPanel);
    expect(screen.getByText('FORBUSH INDICATOR')).toBeTruthy();
  });

  it('shows the Quiet state with a status-green dot', async () => {
    const { container } = render(ForbushPanel);
    setForbush({
      state: 'quiet',
      nmdb_drop_pct: 0.5,
      kp: 2,
      solar_wind_kms: 380,
      local_drop_pct: 0,
      detail: 'Quiet · no Forbush decrease detected',
    });
    await tick();
    expect(screen.getByText(/Quiet/i)).toBeTruthy();
    expect(container.querySelector('.status-green')).toBeTruthy();
  });

  it('shows the Watch state with a status-amber dot', async () => {
    const { container } = render(ForbushPanel);
    setForbush({
      state: 'watch',
      nmdb_drop_pct: 3,
      kp: 2,
      solar_wind_kms: 380,
      local_drop_pct: 0,
      detail: 'Watch · cosmic-ray flux declining',
    });
    await tick();
    expect(screen.getByText(/Watch/i)).toBeTruthy();
    expect(container.querySelector('.status-amber')).toBeTruthy();
  });

  it('shows the Forbush in progress state with a status-red dot', async () => {
    const { container } = render(ForbushPanel);
    setForbush({
      state: 'forbush',
      nmdb_drop_pct: 5,
      kp: 6,
      solar_wind_kms: 550,
      local_drop_pct: 4,
      detail: 'Forbush in progress · significant flux drop',
    });
    await tick();
    expect(screen.getByText(/Forbush in progress/i)).toBeTruthy();
    expect(container.querySelector('.status-red')).toBeTruthy();
  });
});
