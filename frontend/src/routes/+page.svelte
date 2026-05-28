<script lang="ts">
  import '../app.css';
  import { onMount, onDestroy } from 'svelte';
  import { initWs } from '$lib/stores/ws';
  import { initHealthPolling } from '$lib/stores/health';
  import Container from '$lib/Container.svelte';
  import CadenceWarningBanner from '$lib/components/CadenceWarningBanner.svelte';
  import HeaderPanel from '$lib/panels/HeaderPanel.svelte';
  import StatsRow from '$lib/panels/StatsRow.svelte';
  import MuonChart from '$lib/panels/MuonChart.svelte';
  import SpaceWeatherPanel from '$lib/panels/SpaceWeatherPanel.svelte';
  import EarthquakeList from '$lib/panels/EarthquakeList.svelte';
  import LightningPanel from '$lib/panels/LightningPanel.svelte';
  import AuroraPanel from '$lib/panels/AuroraPanel.svelte';
  import TemperatureChart from '$lib/panels/TemperatureChart.svelte';
  import HealthRow from '$lib/panels/HealthRow.svelte';

  let cleanupWs: (() => void) | undefined;
  let cleanupHealth: (() => void) | undefined;

  onMount(() => {
    cleanupWs = initWs();
    cleanupHealth = initHealthPolling();
  });

  onDestroy(() => {
    cleanupWs?.();
    cleanupHealth?.();
  });
</script>

<svelte:head>
  <title>Observatory — Dashboard</title>
</svelte:head>

<Container>
  <CadenceWarningBanner />
  <HeaderPanel />
  <StatsRow />
  <MuonChart />
  <SpaceWeatherPanel />
  <div class="two-col">
    <EarthquakeList />
    <LightningPanel />
  </div>
  <AuroraPanel />
  <TemperatureChart />
  <HealthRow />
</Container>

<style>
  :global(.is-stale-amber) { opacity: 0.6; transition: opacity 0.3s ease; }
  :global(.is-stale-red)   { opacity: 0.6; transition: opacity 0.3s ease; }

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
