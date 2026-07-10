<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { indoorStore } from '$lib/stores/indoor';
  import { fetchIndoorHistory } from '$lib/api/rest';
  import { buildIndoorCo2Plot } from '$lib/charts/plotHelpers';
  import type { IndoorNode, IndoorPoint } from '$lib/types';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let historyTimer: ReturnType<typeof setInterval> | undefined;
  let history: IndoorPoint[] = [];

  // Single node for now — take the first. Multi-node is a later iteration.
  $: node = ($indoorStore.current?.nodes?.[0] ?? undefined) as IndoorNode | undefined;
  $: co2 = node?.co2_ppm ?? null;
  $: stale = node != null && node.age_sec > 15 * 60; // > 15 min since last reading
  $: band = co2 == null ? 'unknown' : co2 < 800 ? 'good' : co2 < 1200 ? 'moderate' : 'poor';
  $: bandLabel = {
    good: 'Fresh',
    moderate: 'Stuffy — consider airing',
    poor: 'Ventilate the room',
    unknown: '—',
  }[band];
  $: roomLabel = (node?.node_id ?? 'indoor').replace(/-/g, ' ').toUpperCase();

  const fmt = (v: number | null | undefined, d: number, unit: string): string =>
    v == null ? '—' : `${v.toFixed(d)}${unit}`;

  function render() {
    if (!container) return;
    container.innerHTML = '';
    container.appendChild(buildIndoorCo2Plot(history, container.clientWidth || 600));
  }

  async function bootstrap() {
    try {
      const res = await fetchIndoorHistory(24);
      history = res.rows;
      render();
    } catch {
      /* leave empty — chart renders empty axes */
    }
  }

  onMount(() => {
    bootstrap();
    historyTimer = setInterval(bootstrap, 60_000);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(render);
      if (container) observer.observe(container);
    }
  });

  onDestroy(() => {
    if (observer) observer.disconnect();
    if (historyTimer) clearInterval(historyTimer);
    if (container) container.innerHTML = '';
  });
</script>

<section class="section">
  <ChartHeader title="INDOOR AIR" sensor={roomLabel} />

  {#if node}
    <div class="hero" class:stale>
      <div class="co2 band-{band}">
        <span class="value">{co2 ?? '—'}</span>
        <span class="unit">ppm CO₂</span>
      </div>
      <div class="verdict band-{band}">{stale ? 'No recent reading' : bandLabel}</div>
    </div>

    <div class="stats">
      <div><span class="s-val">{fmt(node.temp_c, 1, '°C')}</span><span class="s-lbl">temp</span></div>
      <div><span class="s-val">{fmt(node.humidity_pct, 0, '%')}</span><span class="s-lbl">humidity</span></div>
      <div><span class="s-val">{fmt(node.pressure_hpa, 0, ' hPa')}</span><span class="s-lbl">pressure</span></div>
    </div>

    <div bind:this={container} data-chart="indoor-co2" class="chart-container"></div>
  {:else}
    <p class="empty">Waiting for the indoor node…</p>
  {/if}
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .hero {
    display: flex;
    align-items: baseline;
    gap: 16px;
    flex-wrap: wrap;
    margin: 4px 0 10px;
  }
  .hero.stale {
    opacity: 0.6;
  }
  .co2 {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .co2 .value {
    font-size: 3rem;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .co2 .unit {
    font-size: 0.9rem;
    color: var(--text-muted, #5a5a5a);
  }
  .verdict {
    font-size: 0.95rem;
    font-weight: 500;
  }
  /* Traffic-light bands. */
  .band-good {
    color: var(--accent, #6b8e6b);
  }
  .band-moderate {
    color: #c2913b;
  }
  .band-poor {
    color: #c0563f;
  }
  .band-unknown {
    color: var(--text-muted, #5a5a5a);
  }
  .stats {
    display: flex;
    gap: 32px;
    margin-bottom: 8px;
  }
  .stats div {
    display: flex;
    flex-direction: column;
  }
  .s-val {
    font-size: 1.2rem;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .s-lbl {
    font-size: 0.75rem;
    color: var(--text-muted, #5a5a5a);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .chart-container {
    width: 100%;
    min-height: 180px;
  }
  .empty {
    color: var(--text-muted, #5a5a5a);
    font-size: 0.9rem;
    padding: 12px 0 40px;
  }
</style>
