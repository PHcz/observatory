<script lang="ts">
  // Consistent chart header across all panels:
  //   [green TITLE]  [time period]            [SENSOR]
  //   ^-- left-aligned pair --^      right-aligned --^
  export let title: string; // e.g. "PRESSURE" (already in display case)
  export let sensor: string; // e.g. "OUTSIDE SENSOR" / "PICO µ" / "NOAA SWPC"
  // Time period sits between title and source. Graph panels use the default;
  // non-graph panels pass `period={null}` to omit it (title left, source right).
  export let period: string | null = 'last 24 hours';
</script>

<header class="chart-header">
  <span class="title">{title}</span>
  {#if period}<span class="period">{period}</span>{/if}
  <span class="sensor">{sensor}</span>
</header>

<style>
  .chart-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
  }
  /* Green title — the only accent in the header. */
  .title {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    white-space: nowrap;
  }
  /* Time period — muted, sits right of the title. */
  .period {
    font-size: 11px;
    font-weight: 400;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    white-space: nowrap;
  }
  /* Sensor name — muted, pushed to the right edge. No text-transform so the
     µ in "PICO µ" renders as the micro sign, not an uppercased Greek mu. */
  .sensor {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--text-muted);
    margin-left: auto;
    white-space: nowrap;
  }
</style>
