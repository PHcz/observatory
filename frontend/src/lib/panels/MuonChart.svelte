<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { muonStore, flushMuonBuffer, seedMuonHistory } from '$lib/stores/muon';
  import { fetchMuonHistory } from '$lib/api/rest';
  import { buildMuonPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import { startReseed } from '$lib/utils/reseed';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let intervalId: ReturnType<typeof setInterval> | undefined;
  let unsubscribe: (() => void) | undefined;
  let stopReseed: (() => void) | undefined;

  function render() {
    if (!container) return;
    const state = $muonStore;
    container.innerHTML = '';
    container.appendChild(buildMuonPlot(state.history, container.clientWidth || 600));
  }

  async function bootstrap() {
    const now = Math.floor(Date.now() / 1000);
    try {
      const rows = await fetchMuonHistory(now - 86400, now);
      seedMuonHistory(rows);
    } catch {
      setTimeout(async () => {
        try {
          const rows2 = await fetchMuonHistory(
            Math.floor(Date.now() / 1000) - 86400,
            Math.floor(Date.now() / 1000)
          );
          seedMuonHistory(rows2);
        } catch {
          /* leave empty — chart will render empty axes */
        }
      }, 5000);
    }
  }

  onMount(() => {
    bootstrap();
    // Reconcile with the server (authoritative SQLite per-minute counts)
    // periodically + on tab-refocus, so lossy live-WS accumulation can't drift
    // the chart into spurious near-zero spikes over a long unrefreshed session.
    stopReseed = startReseed(bootstrap);
    unsubscribe = muonStore.subscribe(render);
    intervalId = setInterval(flushMuonBuffer, 1000);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(render);
      if (container) observer.observe(container);
    }
  });

  $: muonHealth = $healthStore.data?.local?.muon;
  $: muonLastTs = $muonStore.history.length > 0
    ? $muonStore.history[$muonStore.history.length - 1].ts
    : muonHealth?.last_event_ts ?? null;
  $: muonLevel = (muonLastTs != null && muonHealth?.staleness_threshold_sec)
    ? deriveStaleness(ageSeconds(muonLastTs), muonHealth.staleness_threshold_sec)
    : 'fresh';

  // ENH-02: anomaly badge — count of bins with a non-null severity flag.
  $: anomalyCount = $muonStore.history.filter(r => r.anomaly_severity != null).length;

  onDestroy(() => {
    if (intervalId) clearInterval(intervalId);
    if (stopReseed) stopReseed();
    if (observer) observer.disconnect();
    if (unsubscribe) unsubscribe();
    if (container) container.innerHTML = '';
  });
</script>

<section class="section" class:is-stale-amber={muonLevel === 'amber'} class:is-stale-red={muonLevel === 'red'}>
  <ChartHeader title="MUONS" sensor="PICO µ" />
  <p class="section-sub">Events per minute · raw, not dead-time corrected · atmospheric pressure corrected</p>
  {#if anomalyCount > 0}
    <p class="anomaly-badge">! {anomalyCount} {anomalyCount === 1 ? 'anomaly' : 'anomalies'}</p>
  {/if}
  <!-- WS-pushed source: caption permanently hidden, UI-14 -->
  <StalenessCaption lastTs={muonLastTs} level="fresh" />
  <div bind:this={container} data-chart="muon" class="chart-container"></div>
</section>

<style>
  .section {
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
  }
  /* Header is the shared ChartHeader atom; caption-placement (UI-15) preserved:
     StalenessCaption renders below the section-sub (WS-pushed source hardcoded
     level='fresh', so the caption is permanently suppressed). */
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0 0 8px 0;
  }
  /* ENH-02: anomaly badge — visible when |z|>3 bins are present. */
  .anomaly-badge {
    font-size: 11px;
    color: var(--warn);
    border-left: 4px solid var(--warn);
    padding-left: 8px;
    margin: 0 0 16px 0;
  }
  .chart-container {
    width: 100%;
    min-height: 240px;
  }
</style>
