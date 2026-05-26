<script lang="ts">
  import { healthStore } from '$lib/stores/health';
  import { wsStatus } from '$lib/stores/ws';
  import StatusDot from '$lib/atoms/StatusDot.svelte';
  import { formatAgeCaption } from '$lib/utils/time';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import type { SourceHealth } from '$lib/types';

  type DotColor = 'green' | 'amber' | 'red';

  interface SourceEntry {
    key: string;
    group: 'local' | 'external' | 'ws';
    label: string;
  }

  const SOURCES: SourceEntry[] = [
    { key: 'weather',     group: 'local',    label: 'Weather node' },
    { key: 'muon',        group: 'local',    label: 'Muon detector' },
    { key: 'usgs',        group: 'external', label: 'USGS' },
    { key: 'emsc',        group: 'external', label: 'EMSC' },
    { key: 'bgs',         group: 'external', label: 'BGS' },
    { key: 'noaa',        group: 'external', label: 'NOAA' },
    { key: 'blitzortung', group: 'external', label: 'Lightning' },
    { key: 'aurora',      group: 'external', label: 'AuroraWatch' },
    { key: 'live-updates', group: 'ws',      label: 'Live updates' },
  ];

  function getSourceHealth(entry: SourceEntry): SourceHealth | null {
    const data = $healthStore.data;
    if (!data) return null;
    if (entry.group === 'local') {
      return (data.local as Record<string, SourceHealth>)[entry.key] ?? null;
    }
    if (entry.group === 'external') {
      return (data.external as Record<string, SourceHealth>)[entry.key] ?? null;
    }
    return null;
  }

  function getDotColor(entry: SourceEntry): DotColor {
    if (entry.group === 'ws') {
      if ($wsStatus === 'connected') return 'green';
      if ($wsStatus === 'connecting') return 'amber';
      return 'red';
    }
    const sh = getSourceHealth(entry);
    if (!sh) return 'red';
    if (sh.freshness === 'healthy') return 'green';
    if (sh.freshness === 'stale') return 'amber';
    if (sh.freshness === 'down') return 'red';
    // fallback: derive from age
    if (sh.last_event_ts == null) return 'red';
    const level = deriveStaleness(ageSeconds(sh.last_event_ts), sh.staleness_threshold_sec);
    return level === 'fresh' ? 'green' : level;
  }

  function getCaption(entry: SourceEntry): string {
    if (entry.group === 'ws') {
      if ($wsStatus === 'connected') return 'connected';
      if ($wsStatus === 'connecting') return 'reconnecting';
      return 'disconnected';
    }
    const sh = getSourceHealth(entry);
    if (!sh || sh.last_event_ts == null) return 'never';
    return `last seen ${formatAgeCaption(sh.last_event_ts)}`;
  }
</script>

<footer class="health-row">
  {#each SOURCES as entry (entry.key)}
    <div class="health-entry">
      <StatusDot status={getDotColor(entry)} />
      <div class="health-label">{entry.label}</div>
      <div class="health-caption">{getCaption(entry)}</div>
    </div>
  {/each}
</footer>

<style>
  .health-row {
    display: flex;
    flex-wrap: wrap;
    gap: 32px;
    border-top: 1px solid var(--border);
    padding-top: 32px;
    margin-top: 80px;
  }

  .health-entry {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    min-width: 80px;
  }

  @media (max-width: 900px) {
    .health-row {
      gap: 16px;
      margin-top: 48px;
    }
    .health-entry {
      min-width: 0;
    }
  }

  .health-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
  }

  .health-caption {
    font-size: 11px;
    color: var(--text-muted);
  }
</style>
