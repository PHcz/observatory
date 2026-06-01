<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { weatherStore, seedWeatherHistory } from '$lib/stores/weather';
  import { fetchWeatherHistory } from '$lib/api/rest';
  import { buildHumidityDewpointPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { themeStore } from '$lib/stores/theme';
  import { startReseed } from '$lib/utils/reseed';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let unsubWeather: (() => void) | undefined;
  let unsubTheme: (() => void) | undefined;
  let stopReseed: (() => void) | undefined;

  function render() {
    if (!container) return;
    container.innerHTML = '';
    container.appendChild(buildHumidityDewpointPlot($weatherStore.history, container.clientWidth || 600));
  }

  async function bootstrap() {
    const now = Math.floor(Date.now() / 1000);
    try {
      const rows = await fetchWeatherHistory(now - 86400, now);
      seedWeatherHistory(rows);
    } catch {
      // leave empty — chart will render empty axes
    }
  }

  onMount(() => {
    bootstrap();
    stopReseed = startReseed(bootstrap); // reconcile w/ server periodically + on tab-refocus
    unsubWeather = weatherStore.subscribe(render);
    unsubTheme = themeStore.subscribe(render);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(render);
      if (container) observer.observe(container);
    }
  });

  $: weatherHealth = $healthStore.data?.local?.weather;
  $: lastTs = $weatherStore.current?.ts ?? weatherHealth?.last_event_ts ?? null;

  onDestroy(() => {
    observer?.disconnect();
    unsubWeather?.();
    unsubTheme?.();
    stopReseed?.();
    if (container) container.innerHTML = '';
  });
</script>

<section class="section" data-testid="humidity-chart">
  <header class="section-header">
    <div class="eyebrow">HUMIDITY</div>
    <div class="section-title">Humidity today</div>
    <div class="section-meta">Outside sensor</div>
  </header>
  <p class="section-subtitle">Relative humidity (solid) and dew point (sage), past 24 hours.</p>
  <p class="dewpoint-guide">Dew point: under 10°C dry · 15–18°C sticky · 20°C+ muggy</p>
  <StalenessCaption {lastTs} level="fresh" />
  <div bind:this={container} class="chart-container"></div>
</section>

<style>
  .section { margin-bottom: 80px; }
  .section-header {
    display: flex; align-items: baseline; gap: 16px;
    padding-bottom: 16px; border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
  }
  .eyebrow {
    font-size: 11px; font-weight: 600; letter-spacing: 0.20em;
    color: var(--accent-soft); text-transform: uppercase;
  }
  .section-title { font-size: 16px; font-weight: 600; color: var(--text); }
  .section-meta {
    font-size: 11px; font-weight: 600; letter-spacing: 0.20em;
    color: var(--accent-soft); margin-left: auto;
  }
  .section-subtitle { font-size: 13px; color: var(--text-muted); margin: 0 0 24px; }
  .dewpoint-guide {
    font-size: 11px; color: var(--text-muted); margin: 0 0 12px 0; font-style: normal;
  }
  .chart-container { width: 100%; min-height: 180px; }
  @media (max-width: 600px) { .section { margin-bottom: 48px; } }
</style>
