<script lang="ts">
  import { earthquakeStore } from '$lib/stores/earthquakes';
  import MagnitudePill from '$lib/atoms/MagnitudePill.svelte';
  import SourceBadge from '$lib/atoms/SourceBadge.svelte';
  import { formatAgeCaption } from '$lib/utils/time';

  const MAX_ROWS = 10;

  $: recent = $earthquakeStore.recent;
  $: displayed = recent.slice(0, MAX_ROWS);
  $: hasMore = recent.length > MAX_ROWS;
</script>

<section class="earthquake-list">
  <header class="section-header">
    <div class="section-title-row">
      <h2 class="section-title">Earthquakes</h2>
      <span class="section-meta">USGS · EMSC</span>
    </div>
    <p class="section-sub">Magnitude 4.0+ globally, all detectable UK events</p>
  </header>

  {#if displayed.length === 0}
    <p class="empty">No earthquakes on record yet.</p>
  {:else}
    <div class="quake-rows">
      {#each displayed as e}
        <div class="quake-row">
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
      <p class="more-caption">(showing 10 of {recent.length})</p>
    {/if}
  {/if}
</section>

<style>
  .earthquake-list {
    margin-bottom: 80px;
  }

  .section-header {
    margin-bottom: 24px;
  }

  .section-title-row {
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin-bottom: 8px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  .section-meta {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
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
</style>
