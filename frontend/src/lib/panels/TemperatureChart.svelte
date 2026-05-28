<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { weatherStore, seedWeatherHistory } from '$lib/stores/weather';
  import { fetchWeatherHistory } from '$lib/api/rest';
  import { buildTempPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let unsubscribe: (() => void) | undefined;

  function render() {
    if (!container) return;
    const state = $weatherStore;
    container.innerHTML = '';
    container.appendChild(buildTempPlot(state.history, container.clientWidth || 600));
  }

  async function bootstrap() {
    const now = Math.floor(Date.now() / 1000);
    try {
      const rows = await fetchWeatherHistory(now - 86400, now);
      seedWeatherHistory(rows);
    } catch {
      setTimeout(async () => {
        try {
          const rows2 = await fetchWeatherHistory(
            Math.floor(Date.now() / 1000) - 86400,
            Math.floor(Date.now() / 1000)
          );
          seedWeatherHistory(rows2);
        } catch {
          /* leave empty — chart will render empty axes */
        }
      }, 5000);
    }
  }

  onMount(() => {
    bootstrap();
    unsubscribe = weatherStore.subscribe(render);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(render);
      if (container) observer.observe(container);
    }
  });

  $: weatherHealth = $healthStore.data?.local?.weather;
  $: tempLastTs = $weatherStore.current?.ts ?? weatherHealth?.last_event_ts ?? null;
  $: tempLevel = (tempLastTs != null && weatherHealth?.staleness_threshold_sec)
    ? deriveStaleness(ageSeconds(tempLastTs), weatherHealth.staleness_threshold_sec)
    : 'fresh';

  onDestroy(() => {
    if (observer) observer.disconnect();
    if (unsubscribe) unsubscribe();
    if (container) container.innerHTML = '';
  });
</script>

<section class="section" class:is-stale-amber={tempLevel === 'amber'} class:is-stale-red={tempLevel === 'red'}>
  <header class="section-header">
    <div class="section-title">Temperature today</div>
    <div class="section-meta">Outside sensor</div>
  </header>
  <!-- WS-pushed source: caption permanently hidden, UI-14 (same as MuonChart) -->
  <StalenessCaption lastTs={tempLastTs} level="fresh" />
  <div bind:this={container} data-chart="temperature" class="chart-container"></div>
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .section-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  .section-title {
    font-size: 16px;
    font-weight: 600;
  }
  .section-meta {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
  }
  .chart-container {
    width: 100%;
    min-height: 180px;
  }
</style>
