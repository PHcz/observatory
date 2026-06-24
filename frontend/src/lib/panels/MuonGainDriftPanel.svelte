<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import * as Plot from '@observablehq/plot';
  import { muonGainDriftStore } from '$lib/stores/muonGainDrift';
  import { niceFloorDomain } from '$lib/charts/domain';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let unsubscribe: (() => void) | undefined;

  function getTokens() {
    if (typeof document === 'undefined') {
      return { data: '#111111', raw: '#cccccc', grid: '#f0f0ec' };
    }
    const cs = getComputedStyle(document.documentElement);
    return {
      data: cs.getPropertyValue('--chart-data').trim() || '#111111',
      raw: cs.getPropertyValue('--chart-raw').trim() || '#cccccc',
      grid: cs.getPropertyValue('--chart-grid').trim() || '#f0f0ec',
    };
  }

  $: data = $muonGainDriftStore.data;
  $: isEmpty = !data || data.weeks.length < 1;

  function render() {
    if (!container) return;
    const d = $muonGainDriftStore.data;
    container.innerHTML = '';
    if (!d || d.weeks.length < 1) return;

    const t = getTokens();
    const weeks = d.weeks.map(w => ({
      ...w,
      date: new Date(w.week_start_ts * 1000),
    }));

    // Bracket the weekly peaks + the baseline rule so drift never touches an edge.
    const yScale = niceFloorDomain(
      [...weeks.map((w) => w.mip_peak_adc), d.baseline_adc],
      4,
    );

    const plot = Plot.plot({
      width: container.clientWidth || 600,
      height: 160,
      marginLeft: 60,
      marginRight: 12,
      marginBottom: 28,
      marginTop: 8,
      x: {
        type: 'time',
        label: null,
        tickFormat: (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      },
      y: {
        label: 'MIP peak (ADC units)',
        grid: true,
        ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}),
      },
      marks: [
        Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
        // Dashed baseline reference line
        Plot.ruleY([d.baseline_adc], {
          stroke: t.raw,
          strokeDasharray: '4 3',
          strokeWidth: 1.5,
        }),
        // Weekly MIP-peak line
        Plot.line(weeks, {
          x: 'date',
          y: 'mip_peak_adc',
          stroke: t.data,
          strokeWidth: 2,
          strokeLinejoin: 'round',
          strokeLinecap: 'round',
        }),
        // Weekly MIP-peak dots
        Plot.dot(weeks, {
          x: 'date',
          y: 'mip_peak_adc',
          r: 3,
          fill: t.data,
        }),
      ],
    });
    container.appendChild(plot);
  }

  onMount(() => {
    unsubscribe = muonGainDriftStore.subscribe(render);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(render);
      if (container) observer.observe(container);
    }
  });

  onDestroy(() => {
    if (observer) observer.disconnect();
    if (unsubscribe) unsubscribe();
    if (container) container.innerHTML = '';
  });
</script>

<section class="section">
  <ChartHeader title="MUON GAIN-DRIFT" sensor="PICO µ" period="last 12 weeks" />
  {#if isEmpty}
    <div class="empty-state">Gain-drift tracking begins after the first week of data.</div>
  {/if}
  <div bind:this={container} class="chart-container" class:hidden={isEmpty}></div>
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .chart-container {
    width: 100%;
    min-height: 160px;
  }
  .chart-container.hidden {
    display: none;
  }
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 160px;
    font-size: 13px;
    color: var(--text-muted);
  }
  @media (max-width: 900px) {
    .section {
      margin-bottom: 48px;
    }
  }
</style>
