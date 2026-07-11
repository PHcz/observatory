<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { initWs } from '$lib/stores/ws';
  import { initHealthPolling } from '$lib/stores/health';
  import { initForecastPolling } from '$lib/stores/forecast';
  import { initAirQualityPolling } from '$lib/stores/airQuality';
  import { initIndoorPolling } from '$lib/stores/indoor';
  import { initAlertsPolling } from '$lib/stores/alerts';
  import { initWeatherDerivedPolling } from '$lib/stores/weatherDerived';
  import { initMuonAnalysisPolling } from '$lib/stores/muonAnalysis';
  import { initMuonDiagnosticsPolling } from '$lib/stores/muonDiagnostics';
  import { initMuonGainDriftPolling } from '$lib/stores/muonGainDrift';
  import { initNmdbPolling } from '$lib/stores/nmdb';
  import { initForbushPolling } from '$lib/stores/forbush';
  import { settingsStore } from '$lib/stores/settings';
  import Container from '$lib/Container.svelte';
  import CadenceWarningBanner from '$lib/components/CadenceWarningBanner.svelte';
  import { PANEL_COMPONENTS } from '$lib/panels/registry';
  import { buildRenderPlan } from '$lib/utils/renderPlan';
  import IndoorStatsRow from '$lib/panels/IndoorStatsRow.svelte';
  import IndoorCharts from '$lib/panels/IndoorCharts.svelte';

  let cleanupWs: (() => void) | undefined;
  let cleanupHealth: (() => void) | undefined;
  let cleanupForecast: (() => void) | undefined;
  let cleanupAirQuality: (() => void) | undefined;
  let cleanupIndoor: (() => void) | undefined;
  let cleanupMuonAnalysis: (() => void) | undefined;
  let cleanupMuonDiagnostics: (() => void) | undefined;
  let cleanupMuonGainDrift: (() => void) | undefined;
  let cleanupNmdb: (() => void) | undefined;
  let cleanupForbush: (() => void) | undefined;
  let cleanupAlerts: (() => void) | undefined;
  let cleanupWeatherDerived: (() => void) | undefined;

  onMount(() => {
    cleanupWs = initWs();
    cleanupHealth = initHealthPolling();
    cleanupForecast = initForecastPolling();
    cleanupAirQuality = initAirQualityPolling();
    cleanupIndoor = initIndoorPolling();
    cleanupMuonAnalysis = initMuonAnalysisPolling();
    cleanupMuonDiagnostics = initMuonDiagnosticsPolling();
    cleanupMuonGainDrift = initMuonGainDriftPolling();
    cleanupNmdb = initNmdbPolling();
    cleanupForbush = initForbushPolling();
    cleanupAlerts = initAlertsPolling();
    cleanupWeatherDerived = initWeatherDerivedPolling();
  });

  onDestroy(() => {
    cleanupWs?.();
    cleanupHealth?.();
    cleanupForecast?.();
    cleanupAirQuality?.();
    cleanupIndoor?.();
    cleanupMuonAnalysis?.();
    cleanupMuonDiagnostics?.();
    cleanupMuonGainDrift?.();
    cleanupNmdb?.();
    cleanupForbush?.();
    cleanupAlerts?.();
    cleanupWeatherDerived?.();
  });

  $: plan = buildRenderPlan($settingsStore.order, $settingsStore.panels);
</script>

<svelte:head>
  <title>Observatory — Dashboard</title>
</svelte:head>

<Container>
  <CadenceWarningBanner />
  {#each plan as item (item.kind === 'twocol' ? `twocol:${item.keys.join('+')}` : item.kind === 'indoor' ? 'indoor' : `panel:${item.key}`)}
    {#if item.kind === 'indoor'}
      <IndoorStatsRow />
      <IndoorCharts />
    {:else if item.kind === 'twocol'}
      <div class="two-col">
        {#each item.keys as k (k)}
          {@const TwoColComp = PANEL_COMPONENTS[k]}
          {#if TwoColComp}<svelte:component this={TwoColComp} />{/if}
        {/each}
      </div>
    {:else}
      {@const PanelComp = PANEL_COMPONENTS[item.key]}
      {#if PanelComp}<svelte:component this={PanelComp} />{/if}
    {/if}
  {/each}

  <footer class="dashboard-footer">
    <a href="/settings" class="settings-link" data-sveltekit-reload>Settings</a>
  </footer>
</Container>

<style>
  /* Dim a stale panel's BODY to signal staleness, but keep its ChartHeader
     (<header class="chart-header"> — the green title + source) at full opacity
     so section titles stay consistent regardless of freshness. (A child can't
     be more opaque than a dimmed parent, so the dim must target the body, not
     the whole section.) Panels without a ChartHeader dim all children as before. */
  :global(.is-stale-amber > :not(header)),
  :global(.is-stale-red > :not(header)) { opacity: 0.6; transition: opacity 0.3s ease; }

  .dashboard-footer {
    margin-top: 48px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    text-align: center;
  }
  .settings-link {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
    text-decoration: none;
  }
  .settings-link:hover, .settings-link:focus-visible {
    color: var(--accent);
    text-decoration: underline;
  }
  .settings-link:focus-visible {
    outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 2px;
  }

  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 64px;
    margin-bottom: 80px;
  }

  @media (max-width: 900px) {
    .two-col {
      grid-template-columns: 1fr;
      gap: 48px;
      margin-bottom: 48px;
    }
    :global(.section) { margin-bottom: 48px !important; }
  }
</style>
