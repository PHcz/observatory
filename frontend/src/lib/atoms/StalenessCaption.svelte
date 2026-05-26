<script lang="ts">
  import { formatAgeCaption } from '$lib/utils/time';
  export let lastTs: number | null = null;
</script>

{#if lastTs != null}
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
