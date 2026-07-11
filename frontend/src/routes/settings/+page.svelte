<script lang="ts">
  import { settingsStore } from '$lib/stores/settings';
  import '$lib/stores/theme'; // Activates module-scope themeStore subscription that applies <html data-theme>.
  import type { PanelKey } from '$lib/utils/settingsSchema';
  import ThemeSegmentedControl from '$lib/components/ThemeSegmentedControl.svelte';
  import PanelReorderRow from '$lib/components/PanelReorderRow.svelte';
  import { moveItem } from '$lib/utils/renderPlan';
  import { reorderable } from '$lib/actions/reorderable';

  // UI-SPEC §"Toggle order" — exact row labels (list order now driven by settingsStore.order)
  const PANEL_LABELS: Record<PanelKey, string> = {
    headerPanel: 'Header',
    statsRow: 'Stats',
    todayStrip: 'Today so far (daily summary strip)',
    zambrettiCard: 'Near-term outlook (Zambretti)',
    weatherAlerts: 'Weather alerts (frost & pressure-fall rules)',
    forecast: 'Local forecast',
    airQuality: 'Air quality',
    indoorAir: 'Indoor air (CO₂)',
    muonChart: 'Muon flux chart',
    muonDiagnostics: 'Muon diagnostics (inter-arrival + rate distribution)',
    muonGainDrift: 'Muon gain-drift (weekly MIP-peak tracking)',
    adcSpectrum: 'ADC spectrum',
    barometric: 'Barometric coefficient',
    nmdbOverlay: 'Cosmic ray overlay',
    forbush: 'Forbush indicator',
    spaceWeather: 'Space weather',
    earthquakes: 'Earthquakes',
    lightning: 'Lightning',
    aurora: 'Aurora',
    temperatureChart: 'Temperature chart',
    pressureChart: 'Pressure chart',
    humidityChart: 'Humidity chart',
    lightChart: 'Light chart',
    healthRow: 'System health',
  };

  let announcement = '';

  function reorder(from: number, to: number) {
    settingsStore.update((s) => ({ ...s, order: moveItem(s.order, from, to) }));
    const order = $settingsStore.order;
    announcement = `Moved ${PANEL_LABELS[order[to]]} to position ${to + 1} of ${order.length}`;
  }

  let storageWarning = false;
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem('__obs_probe__', '1');
      window.localStorage.removeItem('__obs_probe__');
    } catch {
      storageWarning = true;
    }
  }

  function handleReset() {
    settingsStore.resetToDefaults();
  }
</script>

<svelte:head>
  <title>Observatory — Settings</title>
</svelte:head>

<main class="settings-page">
  {#if storageWarning}
    <p class="storage-warn">Settings can't be saved in this browser session.</p>
  {/if}

  <a href="/" class="back-link" data-sveltekit-reload>← Dashboard</a>

  <h1>Settings</h1>

  <section class="settings-section" aria-labelledby="theme-eyebrow">
    <div id="theme-eyebrow" class="eyebrow">THEME</div>
    <ThemeSegmentedControl />
  </section>

  <hr class="divider" />

  <section class="settings-section" aria-labelledby="panels-eyebrow">
    <div id="panels-eyebrow" class="eyebrow">PANELS</div>
    <div class="toggle-stack" use:reorderable={{ onReorder: reorder }}>
      {#each $settingsStore.order as key, i (key)}
        <PanelReorderRow
          panelKey={key}
          label={PANEL_LABELS[key]}
          index={i}
          count={$settingsStore.order.length}
          {reorder}
        />
      {/each}
    </div>
    <p class="sr-only" aria-live="polite">{announcement}</p>
  </section>

  <hr class="divider" />

  <a
    href="#reset"
    class="reset-link"
    on:click|preventDefault={handleReset}
    aria-label="Reset all settings to defaults"
  >Reset to defaults</a>

  <p class="footer-hint">Changes save automatically.</p>
</main>

<style>
  .settings-page {
    max-width: 720px;
    margin: 0 auto;
    padding: 48px 24px;
    color: var(--text);
    background: var(--bg);
    min-height: 100vh;
  }
  .back-link {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: var(--accent);
    text-decoration: none;
    display: inline-block;
    margin-bottom: 24px;
  }
  .back-link:hover, .back-link:focus-visible { text-decoration: underline; }
  .back-link:focus-visible {
    outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 2px;
  }
  h1 {
    font-size: 28px;
    font-weight: 400;
    margin: 0 0 48px;
    color: var(--text);
  }
  .settings-section { margin: 0; }
  .eyebrow {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
    margin-bottom: 24px;
  }
  .divider {
    border: 0;
    border-top: 1px solid var(--border);
    margin: 48px 0;
  }
  .toggle-stack {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .toggle-stack :global(.reorder-dragging) {
    opacity: 0.5;
  }
  .toggle-stack :global(.reorder-over-before) {
    box-shadow: inset 0 2px 0 0 var(--accent);
  }
  .toggle-stack :global(.reorder-over-after) {
    box-shadow: inset 0 -2px 0 0 var(--accent);
  }
  .reset-link {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    text-decoration: none;
    display: inline-block;
    padding: 4px 0;
  }
  .reset-link:hover, .reset-link:focus-visible { text-decoration: underline; }
  .reset-link:focus-visible {
    outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 2px;
  }
  .footer-hint {
    font-size: 12px;
    font-weight: 400;
    color: var(--text-muted);
    margin: 24px 0 0;
  }
  .storage-warn {
    font-size: 13px;
    color: var(--warn);
    background: var(--bg-elevated);
    padding: 12px 16px;
    border-radius: 4px;
    margin: 0 0 24px;
  }
  .sr-only {
    position: absolute;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
</style>
