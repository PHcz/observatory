<script lang="ts">
  import { lightningStore } from '$lib/stores/lightning';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  $: summary = $lightningStore.summary;
  // /api/lightning/summary now emits hourly_buckets (Phase 8 Plan 08-07). Read
  // from summary.hourly_buckets first; fall back to state-level hourlyBuckets
  // (legacy Phase 7 path); final fallback is 24 zeros so the SVG always renders
  // a stable bar count. setLightning's spread-merge (Plan 07-13) preserves
  // hourly_buckets across partial WS frames that omit it.
  $: summaryBuckets = summary?.hourly_buckets;
  $: hourlyBuckets = (summaryBuckets && summaryBuckets.length === 24)
    ? summaryBuckets
    : ($lightningStore.hourlyBuckets.length === 24
        ? $lightningStore.hourlyBuckets
        : new Array(24).fill(0));

  $: blitz = $healthStore.data?.external?.blitzortung;
  $: blitzLastTs = summary?.ts ?? blitz?.last_event_ts ?? null;
  $: blitzLevel = blitzLastTs != null
    ? deriveStaleness(ageSeconds(blitzLastTs), blitz?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC)
    : 'fresh';

  $: isEmpty = summary == null || summary.past_24h === 0;

  $: maxBucket = Math.max(...hourlyBuckets, 1);
  $: nearestDisplay = summary?.nearest_km != null ? summary.nearest_km.toFixed(0) : '—';

  const CELL_W = 100 / 24;

  // Hour-of-day labels under the sparkline. Bucket[23] is the current hour,
  // bucket[0] is 23 hours ago. Place a few clock-time ticks (matching the
  // dashboard's other charts) centered under their bars.
  function fmtHour(clockHour: number): string {
    const ampm = clockHour < 12 ? 'AM' : 'PM';
    let h = clockHour % 12;
    if (h === 0) h = 12;
    return `${h}${ampm}`;
  }
  $: axisTicks = (() => {
    const nowHour = new Date().getHours();
    return [0, 6, 12, 18, 23].map((i) => {
      const hoursAgo = 23 - i;
      const clockHour = ((nowHour - hoursAgo) % 24 + 24) % 24;
      return { left: (i + 0.5) * CELL_W, label: fmtHour(clockHour) };
    });
  })();
</script>

<section class="lightning-panel" class:is-stale-amber={blitzLevel === 'amber'} class:is-stale-red={blitzLevel === 'red'}>
  <ChartHeader title="LIGHTNING" sensor="BLITZORTUNG · EUROPE" period={null} />
  <p class="section-sub">Real-time strike detection across Europe</p>
  <StalenessCaption lastTs={blitzLastTs} level={blitzLevel} />

  {#if isEmpty}
    <p class="empty">No strikes in the last 24h.</p>
  {:else}
    <div class="metrics-row">
      <div class="metric-cell">
        <span class="metric-label">Past hour</span>
        <span class="metric-value lightning-num">{summary?.past_hour ?? '—'}</span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">Past 24h</span>
        <span class="metric-value lightning-num">{summary?.past_24h ?? '—'}</span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">Nearest today</span>
        <span class="metric-value nearest-value event-value-bold">{nearestDisplay}</span>
        {#if summary?.nearest_km != null}
          <span class="metric-unit">km</span>
        {/if}
      </div>
    </div>

    <div class="sparkline-section">
      <svg viewBox="0 0 100 80" preserveAspectRatio="none" class="sparkline-svg" aria-hidden="true">
        {#each hourlyBuckets as bucket, i}
          {@const height = maxBucket > 0 ? (bucket / maxBucket) * 80 : 0}
          {@const x = i * CELL_W}
          {@const y = 80 - height}
          <rect
            x={x}
            y={y}
            width={CELL_W - 0.5}
            height={height}
            fill="#5a6b5a"
          />
        {/each}
      </svg>
      <div class="sparkline-axis" aria-hidden="true">
        {#each axisTicks as tick}
          <span class="axis-tick" style="left: {tick.left}%">{tick.label}</span>
        {/each}
      </div>
      <span class="sparkline-label">STRIKES/HR · LAST 24H</span>
    </div>
  {/if}
</section>

<style>
  .lightning-panel {
    padding: 0;
    /* token: section-bottom-margin (UI-15) — Phase 7 plan 07-14 placed this on
     +page.svelte's section wrapper rather than on the panel itself; preserve
     external placement (panel root keeps 0 margin to avoid double-stacking). */
  }

  /* token: subtitle-bottom-margin (UI-15) — diverges from spec (12px) to 16px
     because LightningPanel's StalenessCaption renders between .section-sub and
     .metrics-row; 16px keeps the caption visually grouped with the sub rather
     than floating into the metrics. caption-placement: below — StalenessCaption
     rendered after section-sub. Flagged for follow-up. */
  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    margin-bottom: 16px;
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
  }

  .metrics-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    /* token: metric-row-gap (UI-15) — matches spec (24px) */
    gap: 24px;
    margin-bottom: 16px;
  }

  @media (max-width: 600px) {
    .metrics-row {
      grid-template-columns: 1fr;
      gap: 16px;
    }
  }

  .metric-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .metric-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
  }

  .lightning-num {
    font-size: 28px;
    font-weight: 400;
    line-height: 1.0;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }

  .event-value-bold {
    font-size: 18px;
    font-weight: 600;
    line-height: 1.0;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }

  .metric-unit {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .sparkline-section {
    padding-top: 8px;
  }

  .sparkline-svg {
    width: 100%;
    height: 80px;
    display: block;
  }

  .sparkline-axis {
    position: relative;
    height: 16px;
    margin-top: 2px;
  }
  .axis-tick {
    position: absolute;
    transform: translateX(-50%);
    font-size: 11px;
    font-weight: 400;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .sparkline-label {
    display: block;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    margin-top: 4px;
  }
</style>
