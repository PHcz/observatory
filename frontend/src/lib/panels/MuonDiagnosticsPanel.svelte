<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import * as Plot from '@observablehq/plot';
  import { muonDiagnosticsStore } from '$lib/stores/muonDiagnostics';
  import { niceFloorDomain } from '$lib/charts/domain';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  // 0-anchored y config (bars start at 0) with a labelled tick strictly above
  // the tallest bar / overlay point, so neither touches the top edge.
  function zeroBasedYScale(values: number[]) {
    const ns = niceFloorDomain(values, 4);
    if (!ns) return null;
    return { domain: [0, ns.domain[1]] as [number, number], ticks: ns.ticks.filter((v) => v >= 0) };
  }

  let containerA: HTMLDivElement | undefined;
  let containerB: HTMLDivElement | undefined;
  let observerA: ResizeObserver | undefined;
  let observerB: ResizeObserver | undefined;
  let unsubscribe: (() => void) | undefined;

  function getTokens() {
    if (typeof document === 'undefined') {
      return { raw: '#cccccc', accent: '#6b8e6b', textMuted: '#5a5a5a', grid: '#f0f0ec' };
    }
    const cs = getComputedStyle(document.documentElement);
    return {
      raw: cs.getPropertyValue('--chart-raw').trim() || '#cccccc',
      accent: cs.getPropertyValue('--accent').trim() || '#6b8e6b',
      textMuted: cs.getPropertyValue('--text-muted').trim() || '#5a5a5a',
      grid: cs.getPropertyValue('--chart-grid').trim() || '#f0f0ec',
    };
  }

  $: data = $muonDiagnosticsStore.data;
  // Empty state: no data yet, or sample_size_minutes < 60 (too little data for meaningful diagnostics)
  $: isEmptyA = !data || data.dt_histogram.length === 0 || data.sample_size_minutes < 60;
  $: isEmptyB = !data || data.rate_pmf.length === 0 || data.sample_size_minutes < 60;

  function renderA() {
    if (!containerA) return;
    const d = $muonDiagnosticsStore.data;
    containerA.innerHTML = '';
    if (!d || d.dt_histogram.length === 0 || d.sample_size_minutes < 60) return;

    const t = getTokens();
    const hist = d.dt_histogram;
    const baseRate = d.baseline_rate; // events per minute

    // Theoretical exponential PDF: f(t) = lambda * exp(-lambda * t)
    // lambda = baseline_rate / 60 (convert per-min to per-sec)
    const lambda = baseRate / 60;
    // Overlay line points across the dt range
    const dtMax = hist.length > 0 ? hist[hist.length - 1].bin_s : 5;
    const totalCount = hist.reduce((s, b) => s + b.count, 0);
    const binWidth = hist.length > 1 ? hist[1].bin_s - hist[0].bin_s : 1;
    const expPoints: { bin_s: number; expected: number }[] = [];
    for (let t_s = 0; t_s <= dtMax + binWidth; t_s += dtMax / 80) {
      expPoints.push({
        bin_s: t_s,
        // Scale to match observed histogram area
        expected: lambda * Math.exp(-lambda * t_s) * totalCount * binWidth,
      });
    }

    const yScale = zeroBasedYScale([
      ...hist.map((b) => b.count),
      ...expPoints.map((p) => p.expected),
    ]);

    const plot = Plot.plot({
      width: containerA.clientWidth || 300,
      height: 160,
      marginLeft: 40,
      marginRight: 8,
      marginBottom: 28,
      marginTop: 8,
      x: { label: 'Δt (s)' },
      y: { label: null, grid: true, ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}) },
      marks: [
        Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
        Plot.rectY(hist, {
          x1: (b: { bin_s: number; count: number }) => b.bin_s - binWidth / 2,
          x2: (b: { bin_s: number; count: number }) => b.bin_s + binWidth / 2,
          y: 'count',
          fill: t.raw,
          fillOpacity: 0.7,
        }),
        Plot.line(expPoints, {
          x: 'bin_s',
          y: 'expected',
          stroke: t.accent,
          strokeWidth: 2,
          strokeLinejoin: 'round',
          strokeLinecap: 'round',
        }),
      ],
    });
    containerA.appendChild(plot);
  }

  function renderB() {
    if (!containerB) return;
    const d = $muonDiagnosticsStore.data;
    containerB.innerHTML = '';
    if (!d || d.rate_pmf.length === 0 || d.sample_size_minutes < 60) return;

    const t = getTokens();
    const pmf = d.rate_pmf;

    const yScale = zeroBasedYScale([
      ...pmf.map((p) => p.observed_prob),
      ...pmf.map((p) => p.poisson_prob),
    ]);

    const plot = Plot.plot({
      width: containerB.clientWidth || 300,
      height: 160,
      marginLeft: 40,
      marginRight: 8,
      marginBottom: 28,
      marginTop: 8,
      x: { label: 'counts / min' },
      y: {
        label: 'probability',
        grid: true,
        ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}),
      },
      marks: [
        Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
        Plot.rectY(pmf, {
          x1: (p: { count_per_min: number }) => p.count_per_min - 0.5,
          x2: (p: { count_per_min: number }) => p.count_per_min + 0.5,
          y: 'observed_prob',
          fill: t.raw,
          fillOpacity: 0.7,
        }),
        Plot.line(pmf, {
          x: 'count_per_min',
          y: 'poisson_prob',
          stroke: t.accent,
          strokeWidth: 2,
          strokeLinejoin: 'round',
          strokeLinecap: 'round',
        }),
        Plot.dot(pmf, {
          x: 'count_per_min',
          y: 'poisson_prob',
          r: 3,
          fill: t.accent,
        }),
      ],
    });
    containerB.appendChild(plot);
  }

  function render() {
    renderA();
    renderB();
  }

  onMount(() => {
    unsubscribe = muonDiagnosticsStore.subscribe(render);
    if (typeof ResizeObserver !== 'undefined') {
      observerA = new ResizeObserver(renderA);
      observerB = new ResizeObserver(renderB);
      if (containerA) observerA.observe(containerA);
      if (containerB) observerB.observe(containerB);
    }
  });

  onDestroy(() => {
    if (observerA) observerA.disconnect();
    if (observerB) observerB.disconnect();
    if (unsubscribe) unsubscribe();
    if (containerA) containerA.innerHTML = '';
    if (containerB) containerB.innerHTML = '';
  });
</script>

<section class="section">
  <ChartHeader title="MUON DIAGNOSTICS" sensor="PICO µ" />
  <div class="sub-panels">
    <!-- Sub-panel A: inter-arrival time histogram -->
    <div class="sub-panel">
      <p class="sub-label">Inter-arrival time (Δt)</p>
      {#if isEmptyA}
        <div class="empty-state">No muon data yet.</div>
      {/if}
      <div bind:this={containerA} class="chart-container" class:hidden={isEmptyA}></div>
      <p class="legend">Expected exponential (Poisson)</p>
    </div>
    <!-- Sub-panel B: rate vs Poisson PMF -->
    <div class="sub-panel">
      <p class="sub-label">Rate vs Poisson PMF</p>
      {#if isEmptyB}
        <div class="empty-state">No muon data yet.</div>
      {/if}
      <div bind:this={containerB} class="chart-container" class:hidden={isEmptyB}></div>
    </div>
  </div>
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .sub-panels {
    display: flex;
    flex-direction: row;
    gap: 24px;
    align-items: flex-start;
  }
  .sub-panel {
    flex: 1 1 0;
    min-width: 0;
  }
  .sub-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin: 0 0 8px 0;
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
  .legend {
    font-size: 11px;
    color: var(--text-muted);
    margin: 6px 0 0 0;
  }
  @media (max-width: 600px) {
    .sub-panels {
      flex-direction: column;
    }
  }
  @media (max-width: 900px) {
    .section {
      margin-bottom: 48px;
    }
  }
</style>
