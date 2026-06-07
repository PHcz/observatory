<script lang="ts">
  import { settingsStore } from '$lib/stores/settings';
  import '$lib/stores/theme'; // Activates module-scope themeStore subscription that applies <html data-theme>.
  import type { PanelKey } from '$lib/utils/settingsSchema';
  import ThemeSegmentedControl from '$lib/components/ThemeSegmentedControl.svelte';
  import PanelToggleRow from '$lib/components/PanelToggleRow.svelte';

  // UI-SPEC §"Toggle order" — exact 12-row labels in locked order
  const PANEL_LABELS: ReadonlyArray<{ key: PanelKey; label: string }> = [
    { key: 'headerPanel', label: 'Header' },
    { key: 'statsRow', label: 'Stats' },
    { key: 'forecast', label: 'Local forecast' },
    { key: 'airQuality', label: 'Air quality' },
    { key: 'muonChart', label: 'Muon flux chart' },
    { key: 'adcSpectrum', label: 'ADC spectrum' },
    { key: 'barometric', label: 'Barometric coefficient' },
    { key: 'nmdbOverlay', label: 'Cosmic ray overlay' },
    { key: 'forbush', label: 'Forbush indicator' },
    { key: 'spaceWeather', label: 'Space weather' },
    { key: 'earthquakes', label: 'Earthquakes' },
    { key: 'lightning', label: 'Lightning' },
    { key: 'aurora', label: 'Aurora' },
    { key: 'temperatureChart', label: 'Temperature chart' },
    { key: 'pressureChart', label: 'Pressure chart' },
    { key: 'humidityChart', label: 'Humidity chart' },
    { key: 'lightChart', label: 'Light chart' },
    { key: 'healthRow', label: 'System health' },
  ];

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
    <div class="toggle-stack">
      {#each PANEL_LABELS as p (p.key)}
        <PanelToggleRow panelKey={p.key} label={p.label} />
      {/each}
    </div>
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
</style>
