<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { initWs } from '$lib/stores/ws';
  import { initHealthPolling } from '$lib/stores/health';
  import { initForecastPolling } from '$lib/stores/forecast';
  import { initAirQualityPolling } from '$lib/stores/airQuality';
  import { settingsStore } from '$lib/stores/settings';
  import Container from '$lib/Container.svelte';
  import CadenceWarningBanner from '$lib/components/CadenceWarningBanner.svelte';
  import HeaderPanel from '$lib/panels/HeaderPanel.svelte';
  import StatsRow from '$lib/panels/StatsRow.svelte';
  import ForecastPanel from '$lib/panels/ForecastPanel.svelte';
  import AirQualityPanel from '$lib/panels/AirQualityPanel.svelte';
  import MuonChart from '$lib/panels/MuonChart.svelte';
  import SpaceWeatherPanel from '$lib/panels/SpaceWeatherPanel.svelte';
  import EarthquakeList from '$lib/panels/EarthquakeList.svelte';
  import LightningPanel from '$lib/panels/LightningPanel.svelte';
  import AuroraPanel from '$lib/panels/AuroraPanel.svelte';
  import TemperatureChart from '$lib/panels/TemperatureChart.svelte';
  import PressureChart from '$lib/panels/PressureChart.svelte';
  import HumidityChart from '$lib/panels/HumidityChart.svelte';
  import LightChart from '$lib/panels/LightChart.svelte';
  import HealthRow from '$lib/panels/HealthRow.svelte';

  let cleanupWs: (() => void) | undefined;
  let cleanupHealth: (() => void) | undefined;
  let cleanupForecast: (() => void) | undefined;
  let cleanupAirQuality: (() => void) | undefined;

  onMount(() => {
    cleanupWs = initWs();
    cleanupHealth = initHealthPolling();
    cleanupForecast = initForecastPolling();
    cleanupAirQuality = initAirQualityPolling();
  });

  onDestroy(() => {
    cleanupWs?.();
    cleanupHealth?.();
    cleanupForecast?.();
    cleanupAirQuality?.();
  });
</script>

<svelte:head>
  <title>Observatory — Dashboard</title>
</svelte:head>

<Container>
  <CadenceWarningBanner />
  {#if $settingsStore.panels.headerPanel}<HeaderPanel />{/if}
  {#if $settingsStore.panels.statsRow}<StatsRow />{/if}
  {#if $settingsStore.panels.forecast}<ForecastPanel />{/if}
  {#if $settingsStore.panels.airQuality}<AirQualityPanel />{/if}
  {#if $settingsStore.panels.muonChart}<MuonChart />{/if}
  {#if $settingsStore.panels.spaceWeather}<SpaceWeatherPanel />{/if}

  {#if $settingsStore.panels.earthquakes || $settingsStore.panels.lightning}
    <div class="two-col">
      {#if $settingsStore.panels.earthquakes}<EarthquakeList />{/if}
      {#if $settingsStore.panels.lightning}<LightningPanel />{/if}
    </div>
  {/if}

  {#if $settingsStore.panels.aurora}<AuroraPanel />{/if}
  {#if $settingsStore.panels.temperatureChart}<TemperatureChart />{/if}
  {#if $settingsStore.panels.pressureChart}<PressureChart />{/if}
  {#if $settingsStore.panels.humidityChart}<HumidityChart />{/if}
  {#if $settingsStore.panels.lightChart}<LightChart />{/if}
  {#if $settingsStore.panels.healthRow}<HealthRow />{/if}

  <footer class="dashboard-footer">
    <a href="/settings" class="settings-link" data-sveltekit-reload>Settings</a>
  </footer>
</Container>

<style>
  :global(.is-stale-amber) { opacity: 0.6; transition: opacity 0.3s ease; }
  :global(.is-stale-red)   { opacity: 0.6; transition: opacity 0.3s ease; }

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
