<script lang="ts">
  import { formatAgeCaption } from '$lib/utils/time';
  export let lastTs: number | null = null;
  // UI-14: callers can hardcode level="fresh" to permanently suppress the caption
  // for WS-pushed sources (e.g. MuonChart) where staleness is irrelevant.
  export let level: 'fresh' | 'amber' | 'red' | null = null;
</script>

{#if lastTs != null && level !== 'fresh'}
  <span class="staleness">last update: {formatAgeCaption(lastTs)}</span>
{/if}

<style>
  .staleness {
    font-size: 13px;
    color: var(--text-muted);
    display: block;
    margin-top: 4px;
  }
</style>
