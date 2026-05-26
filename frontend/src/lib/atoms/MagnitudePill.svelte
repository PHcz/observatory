<script lang="ts">
  export let magnitude: number | null = null;

  $: tier = magnitude == null || isNaN(magnitude)
    ? 'mag-small'
    : magnitude < 4.0
      ? 'mag-small'
      : magnitude < 6.0
        ? 'mag-mod'
        : 'mag-big';

  $: label = magnitude == null || isNaN(magnitude) ? '—' : magnitude.toFixed(1);
</script>

<span class="magnitude-pill {tier}">{label}</span>

<style>
  .magnitude-pill {
    display: inline-block;
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .mag-small {
    background: var(--border-soft);
    color: var(--text-muted);
  }

  .mag-mod {
    background: #f5e8d8;
    color: var(--warn);
  }

  .mag-big {
    background: #f5dcd8;
    color: var(--alert);
  }
</style>
