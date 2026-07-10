<script lang="ts">
  import { indoorStore } from '$lib/stores/indoor';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { dewPointC, dewComfort } from '$lib/utils/dewpoint';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  $: node = $indoorStore.current?.nodes?.[0] ?? null;
  $: roomLabel = (node?.node_id ?? 'indoor').replace(/-/g, ' ');

  // Staleness — prefer the health source, fall back to the current row's age.
  $: indoorHealth = $healthStore.data?.local?.indoor ?? null;
  $: ageS = node?.age_sec ?? null;
  $: threshold = indoorHealth?.staleness_threshold_sec ?? 240;
  $: level = ageS == null ? 'fresh' : deriveStaleness(ageS, threshold);
  $: lastTs = node?.ts ?? indoorHealth?.last_event_ts ?? null;

  // CO2 traffic-light band.
  $: co2 = node?.co2_ppm ?? null;
  $: band = co2 == null ? 'unknown' : co2 < 800 ? 'good' : co2 < 1200 ? 'moderate' : 'poor';
  $: co2Verdict = { good: 'Fresh', moderate: 'Stuffy — consider airing', poor: 'Ventilate', unknown: '—' }[band];

  const f = (v: number | null | undefined, d: number): string => (v == null ? null : v.toFixed(d)) as string;
  $: co2Str = co2 == null ? null : String(co2);
  $: tempStr = f(node?.temp_c, 1);
  $: humStr = f(node?.humidity_pct, 0);
  $: presStr = f(node?.pressure_hpa, 0);
  $: dewStr =
    node?.temp_c != null && node?.humidity_pct != null
      ? `${dewPointC(node.temp_c, node.humidity_pct)}°C`
      : '—';
  $: dewComfortStr =
    node?.temp_c != null && node?.humidity_pct != null
      ? dewComfort(dewPointC(node.temp_c, node.humidity_pct))
      : null;
</script>

<section
  class="stats-row"
  aria-label="Indoor air"
  class:is-stale-amber={level === 'amber'}
  class:is-stale-red={level === 'red'}
>
  <div class="stat">
    <div class="stat-label">CO₂ · {roomLabel}</div>
    <div class="stat-value band-{band}">
      {#if co2Str !== null}{co2Str}<span class="stat-unit">ppm</span>{:else}—{/if}
    </div>
    <div class="stat-meta">indoor air quality</div>
    <div class="stat-subnote band-{band}">{co2Verdict}</div>
    {#if level !== 'fresh'}<StalenessCaption {lastTs} />{/if}
  </div>

  <div class="stat">
    <div class="stat-label">Temp</div>
    <div class="stat-value">{#if tempStr !== null}{tempStr}<span class="stat-unit">°C</span>{:else}—{/if}</div>
    <div class="stat-meta">indoor · SCD-41 sensor</div>
  </div>

  <div class="stat">
    <div class="stat-label">Humidity</div>
    <div class="stat-value">{#if humStr !== null}{humStr}<span class="stat-unit">%</span>{:else}—{/if}</div>
    <div class="stat-meta">relative · dew point {dewStr}</div>
    {#if dewComfortStr}<div class="stat-subnote comfort">{dewComfortStr}</div>{/if}
  </div>

  <div class="stat">
    <div class="stat-label">Pressure</div>
    <div class="stat-value">{#if presStr !== null}{presStr}{:else}—{/if}</div>
    <div class="stat-meta">hPa · indoor</div>
  </div>
</section>

<style>
  /* Mirrors StatsRow (same tokens/design) so indoor reads as one system. */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 48px;
    margin-bottom: 80px;
  }
  @media (max-width: 900px) {
    .stats-row {
      grid-template-columns: 1fr 1fr;
      gap: 48px;
      margin-bottom: 48px;
    }
  }
  @media (max-width: 600px) {
    .stats-row {
      grid-template-columns: 1fr 1fr;
      gap: 32px 24px;
      align-items: start;
    }
  }
  .stat {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .stat-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.2em;
    color: var(--accent-soft);
    text-transform: uppercase;
    margin-bottom: 0;
  }
  .stat-value {
    font-size: 44px;
    font-weight: 400;
    line-height: 1;
    letter-spacing: -0.035em;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }
  .stat-unit {
    font-size: 24px;
    font-weight: 400;
    margin-left: 2px;
  }
  .stat-meta {
    font-size: 13px;
    font-weight: 400;
    color: var(--text-muted);
    margin-top: 4px;
  }
  .stat-subnote {
    font-size: 11px;
    font-weight: 500;
    margin-top: 4px;
    line-height: 1.4;
  }
  /* Dew-comfort guide — muted, matches the outdoor humidity subnote. */
  .stat-subnote.comfort {
    color: var(--text-muted);
    font-weight: 400;
  }
  /* CO2 traffic-light bands (value + verdict). */
  .band-good {
    color: var(--accent, #6b8e6b);
  }
  .band-moderate {
    color: #c2913b;
  }
  .band-poor {
    color: #c0563f;
  }
  .band-unknown {
    color: var(--text-muted);
  }
</style>
