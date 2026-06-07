<script lang="ts">
  import { formatAgeCaption } from '$lib/utils/time';
  import type { StalenessLevel } from '$lib/utils/staleness';

  export let lastTs: number | null = null;
  /**
   * Source freshness level. When 'fresh' the caption is hidden entirely
   * (UI-14 — WS-pushed live sources don't need a "last update" caption).
   * Default 'amber' preserves the prior "always show if lastTs set" behavior
   * for callers that haven't migrated yet.
   */
  export let level: StalenessLevel = 'amber';
</script>

{#if lastTs != null && level !== 'fresh'}
  <span class="staleness">last update: {formatAgeCaption(lastTs)}</span>
{/if}

<style>
  .staleness {
    font-size: 13px;
    color: var(--text-muted);
    display: block;
    /* 4px groups the caption tightly under the sub-copy above; 16px gives a
       clear gap before the panel data below (was flush — too tight). */
    margin-top: 4px;
    margin-bottom: 16px;
  }
</style>
