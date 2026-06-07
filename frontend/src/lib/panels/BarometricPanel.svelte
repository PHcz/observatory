<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { muonAnalysisStore } from '$lib/stores/muonAnalysis';
  import { buildBarometricScatterPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let unsubscribe: (() => void) | undefined;

  $: data = $muonAnalysisStore.data;
  // No analysis payload at all -> the locked "No muon data yet" empty state.
  $: isEmpty = !data;
  // Fit may be null even with data (too few buckets / too little pressure range);
  // in that case stat values render "—" with the thin-data caveat body, but the
  // header + scatter stay visible.
  $: fit = data?.barometric ?? null;

  // Signed 2 dp + %/hPa suffix; "—" if no fit.
  $: betaDisplay = fit != null ? `${fit.beta >= 0 ? '+' : '−'}${Math.abs(fit.beta).toFixed(2)} %/hPa` : '—';
  $: r2Display = fit != null ? fit.r_squared.toFixed(2) : '—';
  $: pDisplay =
    fit != null ? (fit.p_value < 0.001 ? '< 0.001' : fit.p_value.toFixed(3)) : '—';

  function render() {
    if (!container) return;
    container.innerHTML = '';
    if (isEmpty) return;
    // Scatter points are not surfaced by /api/muon/analysis (v1) — render the
    // fit line on its own when present; the stat cards carry the headline.
    container.appendChild(buildBarometricScatterPlot([], fit, container.clientWidth || 600));
  }

  $: muonHealth = $healthStore.data?.local?.muon;
  $: muonLastTs = muonHealth?.last_event_ts ?? null;
  $: muonLevel =
    muonLastTs != null && muonHealth?.staleness_threshold_sec
      ? deriveStaleness(ageSeconds(muonLastTs), muonHealth.staleness_threshold_sec)
      : 'fresh';

  onMount(() => {
    unsubscribe = muonAnalysisStore.subscribe(render);
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

<section class="section" class:is-stale-amber={muonLevel === 'amber'} class:is-stale-red={muonLevel === 'red'}>
  <ChartHeader title="BAROMETRIC COEFFICIENT" sensor="PICO µ" period="last 7 days" />
  <p class="section-sub">Muon rate falls as atmospheric pressure rises. β captures that pressure response, fitted over the last 7 days from live (uncorrected) rates. Live rate is raw — not dead-time corrected. The offline report is the corrected source of truth.</p>
  <StalenessCaption lastTs={muonLastTs} level={muonLevel} />

  {#if isEmpty}
    <div class="empty-state">
      <p class="empty-heading">No muon data yet</p>
      <p class="empty-body">The PicoMuon detector hasn't logged events yet. Panels populate once 7 days of data accumulate — partial windows show what's available.</p>
    </div>
  {:else}
    <div class="solar-cards">
      <div class="solar-card">
        <div class="solar-card-label">PRESSURE β</div>
        <div class="solar-card-value">{betaDisplay}</div>
        <div class="solar-card-meta">7-day fit · raw rate</div>
      </div>
      <div class="solar-card">
        <div class="solar-card-label">R²</div>
        <div class="solar-card-value">{r2Display}</div>
        <div class="solar-card-meta">goodness of fit · 0–1</div>
      </div>
      <div class="solar-card">
        <div class="solar-card-label">P-VALUE</div>
        <div class="solar-card-value">{pDisplay}</div>
        <div class="solar-card-meta">significance</div>
      </div>
    </div>

    {#if fit == null}
      <p class="thin-data">Not enough pressure range yet for a reliable fit — the coefficient appears once the 7-day window spans a wider pressure swing.</p>
    {/if}

    <div bind:this={container} data-chart="barometric" class="chart-container"></div>
  {/if}
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0 0 24px 0;
  }
  .solar-cards {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 32px;
  }
  .solar-card {
    padding: 32px;
    border: 1px solid var(--border);
    border-radius: 4px;
  }
  .solar-card-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
    margin-bottom: 12px;
  }
  .solar-card-value {
    font-size: 32px;
    font-weight: 400;
    line-height: 1.0;
    color: var(--text);
    font-variant-numeric: tabular-nums;
    margin-bottom: 8px;
  }
  .solar-card-meta {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 8px;
  }
  .thin-data {
    margin-top: 24px;
    font-size: 13px;
    color: var(--text-muted);
    max-width: 640px;
    line-height: 1.5;
  }
  .chart-container {
    width: 100%;
    min-height: 180px;
    margin-top: 32px;
  }
  .empty-state {
    padding: 16px 0;
  }
  .empty-heading {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
    margin: 0 0 8px;
  }
  .empty-body {
    font-size: 13px;
    color: var(--text-muted);
    max-width: 600px;
    line-height: 1.5;
    margin: 0;
  }
  @media (max-width: 900px) {
    .section {
      margin-bottom: 48px;
    }
    .solar-cards {
      grid-template-columns: 1fr;
    }
  }
</style>
