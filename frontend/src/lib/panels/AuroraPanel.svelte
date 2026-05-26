<script lang="ts">
  import { auroraStore } from '$lib/stores/aurora';
  import StatusDot from '$lib/atoms/StatusDot.svelte';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  const AURORA_COPY: Record<'green' | 'yellow' | 'amber' | 'red', string> = {
    green:  'Green · No significant activity',
    yellow: 'Yellow · Minor activity possible',
    amber:  'Amber · Aurora possible tonight',
    red:    'Red · Aurora likely tonight',
  };

  $: data = $auroraStore.current;

  $: auroraHealth = $healthStore.data?.external?.aurora;
  $: auroraLastTs = data?.ts ?? auroraHealth?.last_event_ts ?? null;
  $: auroraLevel = (auroraLastTs != null && auroraHealth?.staleness_threshold_sec)
    ? deriveStaleness(ageSeconds(auroraLastTs), auroraHealth.staleness_threshold_sec)
    : 'fresh';
</script>

<section class="aurora-panel" class:is-stale-amber={auroraLevel === 'amber'} class:is-stale-red={auroraLevel === 'red'}>
  {#if auroraLevel !== 'fresh'}
    <StalenessCaption lastTs={auroraLastTs} />
  {/if}
  <div class="section-header">
    <span class="section-title">Aurora visibility</span>
    <span class="section-meta">AuroraWatch UK · Lancaster</span>
  </div>

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
  }

  .section-header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 16px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--text);
  }

  .section-meta {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
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
