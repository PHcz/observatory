<script lang="ts">
  import { earthquakeStore } from '$lib/stores/earthquakes';
  import MagnitudePill from '$lib/atoms/MagnitudePill.svelte';
  import SourceBadge from '$lib/atoms/SourceBadge.svelte';
  import { formatAgeCaption, ageSeconds } from '$lib/utils/time';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
  import type { StalenessLevel } from '$lib/utils/staleness';

  const MAX_ROWS = 10;

  $: quakeLevel = (() => {
    const ext = $healthStore.data?.external;
    if (!ext) return 'fresh' as StalenessLevel;
    const levels: StalenessLevel[] = (['usgs', 'emsc', 'bgs'] as const).map(k => {
      const s = ext[k];
      if (!s?.last_event_ts || !s?.staleness_threshold_sec) return 'fresh';
      return deriveStaleness(ageSeconds(s.last_event_ts), s.staleness_threshold_sec);
    });
    if (levels.includes('red')) return 'red' as StalenessLevel;
    if (levels.includes('amber')) return 'amber' as StalenessLevel;
    return 'fresh' as StalenessLevel;
  })();

  $: quakeLastTs = (() => {
    const ext = $healthStore.data?.external;
    if (!ext) return null;
    const tsList = (['usgs', 'emsc', 'bgs'] as const)
      .map(k => ext[k]?.last_event_ts ?? null)
      .filter((t): t is number => t != null);
    return tsList.length > 0 ? Math.max(...tsList) : null;
  })();

  $: recent = $earthquakeStore.recent;
  $: filtered = recent.filter(e => e.source === 'bgs' || (e.magnitude != null && e.magnitude >= 3.0));
  $: displayed = filtered.slice(0, MAX_ROWS);
  $: hasMore = filtered.length > MAX_ROWS;
</script>

<section class="earthquake-list" class:is-stale-amber={quakeLevel === 'amber'} class:is-stale-red={quakeLevel === 'red'}>
  <ChartHeader title="EARTHQUAKES" sensor="USGS · EMSC" period={null} />
  <p class="section-sub">Magnitude 3.0+ globally, all detectable UK events</p>
  <StalenessCaption lastTs={quakeLastTs} level={quakeLevel} />

  {#if displayed.length === 0}
    <p class="empty">No earthquakes on record yet.</p>
  {:else}
    <div class="quake-rows">
      {#each displayed as e}
        <div
          class="quake-row"
          class:is-local={e.is_local}
          aria-label={e.is_local ? `Local event: ${e.place ?? ''}` : (e.place ?? '')}
        >
          <MagnitudePill magnitude={e.magnitude} />
          <div class="quake-meta">
            <div class="quake-place">{e.place ?? 'Unknown location'}</div>
            <div class="quake-sub">
              {e.depth_km != null ? `${e.depth_km.toFixed(0)} km depth · ` : ''}<SourceBadge source={e.source} /> · {formatAgeCaption(e.ts)}
            </div>
          </div>
        </div>
      {/each}
    </div>
    {#if hasMore}
      <p class="more-caption">(showing 10 of {filtered.length})</p>
    {/if}
  {/if}
</section>

<style>
  .earthquake-list {
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
  }

  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
  }

  .quake-rows {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .quake-row {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }

  .quake-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .quake-meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .quake-place {
    font-size: 13px;
    color: var(--text);
    font-weight: 400;
  }

  .quake-sub {
    font-size: 12px;
    color: var(--text-muted);
  }

  .more-caption {
    margin-top: 16px;
    font-size: 13px;
    color: var(--text-muted);
  }

  /* UI-18: local-earthquake row visual treatment (Phase 8.5 Plan 05).
     4px sage left border + accent-bg-tint background + bold place text.
     padding-left bumped from default 0 to 16px to compensate for the 4px border
     so the visible text aligns with non-local rows' leading edge.
     Dual-cue (border + weight + tint) satisfies WCAG SC 1.4.1. */
  .quake-row.is-local {
    border-left: 4px solid var(--accent);
    background: var(--accent-bg-tint);
    padding-left: 16px;
  }
  .quake-row.is-local .quake-place {
    font-weight: 600;
  }
</style>
