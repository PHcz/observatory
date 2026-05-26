<script lang="ts">
  export let kpIndex: number | null = null;

  const CELLS = 9;
  $: filled = kpIndex == null ? 0 : Math.max(0, Math.min(CELLS, Math.ceil(kpIndex)));
  $: tier = filled <= 3 ? 'low' : filled <= 5 ? 'mid' : 'high';
</script>

<div class="kp-bar" role="img" aria-label={kpIndex == null ? 'Kp unknown' : `Kp ${kpIndex.toFixed(1)}`}>
  {#each Array(CELLS) as _, i}
    <span
      class="kp-cell"
      class:active-low={i < filled && tier === 'low'}
      class:active-mid={i < filled && tier === 'mid'}
      class:active-high={i < filled && tier === 'high'}
    ></span>
  {/each}
</div>

<style>
  .kp-bar {
    display: flex;
    gap: 4px;
    height: 24px;
  }

  .kp-cell {
    flex: 1;
    border-radius: 2px;
    background: var(--border-soft);
  }

  .active-low {
    background: #b8d4b8;
  }

  .active-mid {
    background: #e8c878;
  }

  .active-high {
    background: #d88068;
  }
</style>
