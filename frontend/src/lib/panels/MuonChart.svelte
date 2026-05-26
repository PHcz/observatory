<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { muonStore, flushMuonBuffer, seedMuonHistory } from '$lib/stores/muon';
  import { fetchMuonHistory } from '$lib/api/rest';
  import { buildMuonPlot } from '$lib/charts/plotHelpers';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  let container: HTMLDivElement | undefined;
  let observer: ResizeObserver | undefined;
  let intervalId: ReturnType<typeof setInterval> | undefined;
  let unsubscribe: (() => void) | undefined;

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

  onDestroy(() => {
    if (intervalId) clearInterval(intervalId);
    if (observer) observer.disconnect();
    if (unsubscribe) unsubscribe();
    if (container) container.innerHTML = '';
  });
</script>

<section class="section" class:is-stale-amber={muonLevel === 'amber'} class:is-stale-red={muonLevel === 'red'}>
  <header class="section-header">
    <div class="section-title">Muons</div>
    <div class="section-meta">Past 24 hours</div>
  </header>
  <p class="section-sub">Events per minute, corrected for atmospheric pressure</p>
  {#if muonLevel !== 'fresh'}
    <StalenessCaption lastTs={muonLastTs} />
  {/if}
  <div bind:this={container} data-chart="muon" class="chart-container"></div>
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
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0 0 24px 0;
  }
  .chart-container {
    width: 100%;
    min-height: 240px;
  }
</style>
