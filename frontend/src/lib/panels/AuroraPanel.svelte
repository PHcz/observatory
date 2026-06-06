<script lang="ts">
  import { auroraStore } from '$lib/stores/aurora';
  import StatusDot from '$lib/atoms/StatusDot.svelte';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  const AURORA_COPY: Record<'green' | 'yellow' | 'amber' | 'red', string> = {
    green:  'Green · No significant activity',
    yellow: 'Yellow · Minor activity possible',
    amber:  'Amber · Aurora possible tonight',
    red:    'Red · Aurora likely tonight',
  };

  $: data = $auroraStore.current;

  $: auroraHealth = $healthStore.data?.external?.aurora;
  $: auroraLastTs = data?.ts ?? auroraHealth?.last_event_ts ?? null;
  $: auroraLevel = auroraLastTs != null
    ? deriveStaleness(ageSeconds(auroraLastTs), auroraHealth?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC)
    : 'fresh';
</script>

<section class="aurora-panel" class:is-stale-amber={auroraLevel === 'amber'} class:is-stale-red={auroraLevel === 'red'}>
  <StalenessCaption lastTs={auroraLastTs} level={auroraLevel} />
  <ChartHeader title="AURORA VISIBILITY" sensor="AURORAWATCH UK · LANCASTER" period={null} />

  {#if data == null}
    <p class="empty">No aurora data yet.</p>
  {:else}
    <div class="aurora-row">
      <StatusDot status={data.status} />
      <span class="aurora-label">{AURORA_COPY[data.status]}</span>
    </div>
    {#if data.detail != null}
      <p class="aurora-detail">{data.detail}</p>
    {/if}
  {/if}
</section>

<style>
  .aurora-panel {
    padding: 0;
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
  }

  @media (max-width: 900px) {
    .aurora-panel {
      /* token: section-bottom-margin (UI-15) — 48px tier at ≤900px (matches spec) */
      margin-bottom: 48px;
    }
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
  }

  .aurora-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding-top: 16px;
  }

  .aurora-label {
    font-size: 13px;
    color: var(--text);
  }

  .aurora-detail {
    font-size: 13px;
    color: var(--text-muted);
    margin-top: 8px;
  }
</style>
