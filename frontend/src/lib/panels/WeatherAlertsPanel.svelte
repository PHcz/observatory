<script lang="ts">
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
  import { alertsStore } from '$lib/stores/alerts';

  $: active = $alertsStore.active;
  $: recent = $alertsStore.recent;

  function relativeAge(ts: number): string {
    const diffSec = Math.floor(Date.now() / 1000) - ts;
    if (diffSec < 60) return 'just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} h ago`;
    return `${Math.floor(diffHr / 24)} d ago`;
  }

  // Rule names: map backend rule identifiers to human-readable display names.
  // Backend sends e.g. "frost_risk" or "rapid_pressure_fall"; display as per UI-SPEC.
  function ruleName(rule: string): string {
    if (rule === 'frost_risk' || rule === 'frost') return 'Frost risk';
    if (rule === 'rapid_pressure_fall' || rule === 'pressure_fall') return 'Rapid pressure fall';
    // Fallback: convert snake_case to Title Case
    return rule.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
</script>

<section class="alerts-panel">
  <ChartHeader title="WEATHER ALERTS" sensor="STATION" period={null} />

  {#if active.length === 0 && recent.length === 0}
    <p class="empty">No alerts in the last 24 hours.</p>
  {:else}
    {#if active.length > 0}
      <div class="section-heading">ACTIVE</div>
      <div class="alert-list">
        {#each active as row (row.id)}
          <div class="alert-row alert-row--{row.severity}">
            <div class="alert-row-body">
              <span class="alert-rule">{ruleName(row.rule)}</span>
              {#if row.detail_text}
                <span class="alert-detail">{row.detail_text}</span>
              {/if}
            </div>
            <span class="alert-ts">{relativeAge(row.crossed_at_ts)}</span>
          </div>
        {/each}
      </div>
    {/if}

    {#if recent.length > 0}
      <div class="section-heading section-heading--spaced">RECENT (24 H)</div>
      <div class="alert-list">
        {#each recent as row (row.id)}
          <div class="alert-row alert-row--resolved">
            <div class="alert-row-body">
              <span class="alert-rule">{ruleName(row.rule)} <span class="resolved-suffix">· resolved</span></span>
              {#if row.detail_text}
                <span class="alert-detail">{row.detail_text}</span>
              {/if}
            </div>
            <span class="alert-ts">{relativeAge(row.crossed_at_ts)}</span>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</section>

<style>
  .alerts-panel {
    margin-bottom: 80px;
  }

  @media (max-width: 900px) {
    .alerts-panel {
      margin-bottom: 48px;
    }
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  .section-heading {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .section-heading--spaced {
    margin-top: 24px;
  }

  .alert-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .alert-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 8px 8px 12px;
    border-left: 4px solid var(--border);
    min-height: 40px;
    box-sizing: border-box;
  }

  /* warn-severity: orange/amber left border */
  .alert-row--warn {
    border-left-color: var(--warn);
  }

  /* alert-severity: red/destructive left border */
  .alert-row--alert {
    border-left-color: var(--alert);
  }

  /* resolved: neutral border */
  .alert-row--resolved {
    border-left-color: var(--border);
  }

  .alert-row-body {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
  }

  .alert-rule {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.4;
  }

  .resolved-suffix {
    font-weight: 400;
    color: var(--text-muted);
  }

  .alert-detail {
    font-size: 13px;
    font-weight: 400;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .alert-ts {
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
    flex-shrink: 0;
    padding-top: 2px;
  }
</style>
