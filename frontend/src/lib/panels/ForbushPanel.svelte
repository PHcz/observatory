<script lang="ts">
  import { forbushStore } from '$lib/stores/forbush';
  import StatusDot from '$lib/atoms/StatusDot.svelte';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
  import type { ForbushState } from '$lib/types';

  // Locked Forbush chip contract (13-UI-SPEC §Forbush chip states).
  const DOT: Record<ForbushState, 'green' | 'amber' | 'red'> = {
    quiet: 'green',
    watch: 'amber',
    forbush: 'red',
  };
  const LABEL: Record<ForbushState, string> = {
    quiet: 'Quiet · no Forbush decrease detected',
    watch: 'Watch · cosmic-ray flux declining',
    forbush: 'Forbush in progress · significant flux drop',
  };

  $: data = $forbushStore.data;
  // Calm-by-default: with no payload yet, present the Quiet chip.
  $: state = (data?.state ?? 'quiet') as ForbushState;
  // The backend supplies the awaiting-data detail line when NMDB is absent.
  $: detail = data?.detail ?? 'Awaiting neutron-monitor data — showing local detector only.';
  // Only render the secondary detail line when it carries new information
  // beyond the chip label (e.g. the NMDB-absent awaiting-data line). When the
  // backend echoes the locked state label as detail, the chip already says it.
  $: showDetail = detail !== LABEL[state];

  // NMDB-source staleness from /api/health external.nmdb (fetched_at fallback).
  $: nmdbHealth = (
    $healthStore.data?.external as
      | Record<string, { last_event_ts: number | null; staleness_threshold_sec: number } | undefined>
      | undefined
  )?.nmdb;
  $: nmdbLastTs = nmdbHealth?.last_event_ts ?? $forbushStore.lastFetchTs ?? null;
  $: nmdbLevel =
    nmdbLastTs != null
      ? deriveStaleness(
          ageSeconds(nmdbLastTs),
          nmdbHealth?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC,
        )
      : 'fresh';
</script>

<section class="section" class:is-stale-amber={nmdbLevel === 'amber'} class:is-stale-red={nmdbLevel === 'red'}>
  <StalenessCaption lastTs={nmdbLastTs} level={nmdbLevel} />
  <ChartHeader title="FORBUSH INDICATOR" sensor="NMDB · OULU + NOAA SWPC" period={null} />
  <p class="section-sub">Driven primarily by the Oulu neutron-monitor drop with NOAA Kp / solar-wind corroboration; the local detector is secondary confirmation only.</p>

  <div class="aurora-row">
    <StatusDot status={DOT[state]} />
    <span class="aurora-label">{LABEL[state]}</span>
  </div>
  {#if showDetail}
    <p class="aurora-detail">{detail}</p>
  {/if}
</section>

<style>
  .section {
    padding: 0;
    margin-bottom: 80px;
  }
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0;
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
  @media (max-width: 900px) {
    .section {
      margin-bottom: 48px;
    }
  }
</style>
