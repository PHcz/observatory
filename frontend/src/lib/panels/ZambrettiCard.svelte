<script lang="ts">
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
  import { weatherDerivedStore } from '$lib/stores/weatherDerived';

  $: outlook = $weatherDerivedStore.outlook;

  // Colour the verdict word per UI-SPEC §5d:
  //   accent  = positive (Settled / Improving / Fine)
  //   warn    = negative (Stormy / Worsening / Unsettled)
  //   text    = neutral  (Changeable / anything else)
  const POSITIVE_VERDICTS = ['Settled', 'Improving', 'Fine', 'Becoming fine', 'Fair', 'Fair, improving', 'Fair, becoming fine'];
  const NEGATIVE_VERDICTS = ['Stormy', 'Worsening', 'Unsettled', 'Stormy, worsening', 'Becoming unsettled', 'Becoming stormy', 'Rain', 'Rain at times', 'Rain at times, worse later', 'Rain at times, better later', 'Showers', 'Showery, becoming more unsettled'];

  $: verdictColour = (() => {
    if (!outlook?.verdict) return 'text';
    const v = outlook.verdict;
    if (POSITIVE_VERDICTS.some((p) => v.toLowerCase().includes(p.toLowerCase()))) return 'accent';
    if (NEGATIVE_VERDICTS.some((n) => v.toLowerCase().includes(n.toLowerCase()))) return 'warn';
    return 'text';
  })();

  $: directionLabel = outlook?.direction ?? null;
</script>

<section class="zambretti-card">
  <ChartHeader title="NEAR-TERM OUTLOOK" sensor="ZAMBRETTI" period={null} />

  {#if !outlook || !outlook.verdict}
    <p class="empty">Insufficient pressure history for forecast.</p>
  {:else}
    <div class="outlook-row">
      <span class="verdict verdict--{verdictColour}">{outlook.verdict}</span>
      {#if directionLabel}
        <span class="detail">Based on {directionLabel} pressure over 3 h</span>
      {/if}
    </div>
  {/if}
</section>

<style>
  .zambretti-card {
    margin-bottom: 24px;
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  .outlook-row {
    display: flex;
    align-items: baseline;
    gap: 16px;
    flex-wrap: wrap;
  }

  .verdict {
    font-size: 20px;
    font-weight: 600;
    line-height: 1.2;
  }

  .verdict--accent {
    color: var(--accent);
  }

  .verdict--warn {
    color: var(--warn);
  }

  .verdict--text {
    color: var(--text);
  }

  .detail {
    font-size: 13px;
    font-weight: 400;
    color: var(--text-muted);
  }
</style>
