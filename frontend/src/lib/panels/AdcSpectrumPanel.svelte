<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { muonAnalysisStore } from '$lib/stores/muonAnalysis';
  import { buildAdcHistogramPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let unsubscribe: (() => void) | undefined;

  $: data = $muonAnalysisStore.data;
  // Empty when there is no analysis payload OR the histogram has no bins yet.
  $: isEmpty = !data || data.adc_histogram.length === 0;

  function render() {
    if (!container) return;
    // Read the store directly (NOT the reactive `data`/`isEmpty` vars): the
    // store.subscribe(render) callback fires before Svelte recomputes `$:`
    // statements, so those vars are stale on the populating update. (MuonChart pattern.)
    const d = $muonAnalysisStore.data;
    container.innerHTML = '';
    if (!d || d.adc_histogram.length === 0) return;
    container.appendChild(buildAdcHistogramPlot(d.adc_histogram, container.clientWidth || 600));
  }

  // Muon-source staleness from /api/health local.muon.
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
  <ChartHeader title="ADC SPECTRUM" sensor="PICO µ" period="last 7 days" />
  <p class="section-sub">Pulse-height distribution over the last 7 days. The modal bin marks the MIP / Landau peak. ADC is uncalibrated (0–1023) — relative, not energy.</p>
  <StalenessCaption lastTs={muonLastTs} level={muonLevel} />

  {#if isEmpty}
    <div class="empty-state">
      <p class="empty-heading">No muon data yet</p>
      <p class="empty-body">The PicoMuon detector hasn't logged events yet. Panels populate once 7 days of data accumulate — partial windows show what's available.</p>
    </div>
  {/if}
  <!-- Container is ALWAYS in the DOM (mirrors MuonChart) so bind:this resolves
       at mount and the reactive build re-runs once data arrives. Harmless /
       0-height while empty. -->
  <div bind:this={container} data-chart="adc-spectrum" class="chart-container"></div>
</section>

<style>
  .section {
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
  }
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0 0 24px 0;
  }
  .chart-container {
    width: 100%;
    min-height: 180px;
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
  }
</style>
