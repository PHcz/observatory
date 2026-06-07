<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { nmdbStore } from '$lib/stores/nmdb';
  import { buildOverlayPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let unsubscribe: (() => void) | undefined;

  $: data = $nmdbStore.data;
  // Empty when there is no payload OR the NMDB reference series is absent.
  $: isEmpty = !data || data.series.length === 0;

  function render() {
    if (!container) return;
    container.innerHTML = '';
    if (isEmpty || !data) return;
    container.appendChild(buildOverlayPlot(data.local, data.series, container.clientWidth || 600));
  }

  // NMDB-source staleness from /api/health external.nmdb (fetched_at fallback),
  // mirroring AirQualityPanel reading external.air_quality.
  $: nmdbHealth = (
    $healthStore.data?.external as
      | Record<string, { last_event_ts: number | null; staleness_threshold_sec: number } | undefined>
      | undefined
  )?.nmdb;
  $: nmdbLastTs = nmdbHealth?.last_event_ts ?? data?.fetched_at ?? null;
  $: nmdbLevel =
    nmdbLastTs != null
      ? deriveStaleness(
          ageSeconds(nmdbLastTs),
          nmdbHealth?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC,
        )
      : 'fresh';

  onMount(() => {
    unsubscribe = nmdbStore.subscribe(render);
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

<section class="section" class:is-stale-amber={nmdbLevel === 'amber'} class:is-stale-red={nmdbLevel === 'red'}>
  <ChartHeader title="COSMIC RAY OVERLAY" sensor="NMDB · OULU" period="last 7 days" />
  <p class="section-sub">Local muon flux and the Oulu neutron monitor, each normalised to % of recent baseline so a Forbush dip lines up across both despite very different absolute count rates.</p>
  <p class="caveat">Live rate is raw — not dead-time corrected. The offline report is the corrected source of truth.</p>
  <StalenessCaption lastTs={nmdbLastTs} level={nmdbLevel} />

  {#if isEmpty}
    <div class="empty-state">
      <p class="empty-heading">Cosmic-ray reference not available yet</p>
      <p class="empty-body">The Oulu neutron-monitor poller hasn't fetched data yet. New counts arrive hourly — the overlay and Forbush indicator populate shortly.</p>
    </div>
  {/if}
  <!-- Container is ALWAYS in the DOM (mirrors MuonChart) so bind:this resolves
       at mount and the reactive build re-runs once data arrives. Harmless /
       0-height while empty. -->
  <div bind:this={container} data-chart="nmdb-overlay" class="chart-container"></div>
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0 0 8px 0;
  }
  .caveat {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
    margin: 0 0 24px 0;
  }
  .chart-container {
    width: 100%;
    min-height: 240px;
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
