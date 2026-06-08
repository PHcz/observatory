<script lang="ts">
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
  import { weatherDerivedStore } from '$lib/stores/weatherDerived';

  $: today = $weatherDerivedStore.today;

  function fmt(n: number | null | undefined, decimals = 1): string {
    return n != null ? n.toFixed(decimals) : '—';
  }

  // Chips are shown as long as the store has loaded (even with partial data).
  // If today is null entirely, the empty state is shown.
  $: chips = today
    ? [
        { label: 'High', value: today.high_c != null ? `${fmt(today.high_c)}°C` : '—' },
        { label: 'Low', value: today.low_c != null ? `${fmt(today.low_c)}°C` : '—' },
        {
          label: 'Pressure',
          value:
            today.pressure_low_hpa != null && today.pressure_high_hpa != null
              ? `${fmt(today.pressure_low_hpa, 0)}–${fmt(today.pressure_high_hpa, 0)} hPa`
              : '—',
        },
        {
          label: 'Peak sun',
          value: today.peak_lux != null ? `${Math.round(today.peak_lux).toLocaleString()} lux` : '—',
        },
        {
          label: 'Dewpoint',
          value:
            today.dewpoint_low_c != null && today.dewpoint_high_c != null
              ? `${fmt(today.dewpoint_low_c)}–${fmt(today.dewpoint_high_c)}°C`
              : '—',
        },
      ]
    : null;
</script>

<section class="today-strip">
  <ChartHeader title="TODAY SO FAR" sensor="OUTSIDE SENSOR" period="since midnight" />

  {#if chips == null}
    <p class="empty">Gathering today's data…</p>
  {:else}
    <div class="chip-row">
      {#each chips as chip (chip.label)}
        <div class="chip">
          <span class="chip-label">{chip.label}</span>
          <span class="chip-value">{chip.value}</span>
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .today-strip {
    margin-bottom: 24px;
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  .chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .chip {
    display: flex;
    align-items: baseline;
    gap: 6px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    line-height: 1.4;
  }

  .chip-label {
    color: var(--text-muted);
    font-weight: 400;
  }

  .chip-value {
    color: var(--text);
    font-weight: 400;
  }
</style>
