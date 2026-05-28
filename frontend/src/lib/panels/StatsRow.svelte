<script lang="ts">
  import { weatherStore, maxLuxToday } from '$lib/stores/weather';
  import { muonStore } from '$lib/stores/muon';
  import { dewPointC } from '$lib/utils/dewpoint';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  $: weather = $weatherStore.current;
  $: muon = $muonStore;

  $: pressureStr = weather?.pressure_hpa != null
    ? weather.pressure_hpa.toFixed(0)
    : null;

  $: pressureMeta = 'hPa · steady';

  $: humidityStr = weather?.humidity_pct != null
    ? weather.humidity_pct.toFixed(0)
    : null;

  $: dewPtStr = (weather?.temp_c != null && weather?.humidity_pct != null)
    ? `${dewPointC(weather.temp_c, weather.humidity_pct)}°C`
    : '—';

  $: humidityMeta = `steady · dew point ${dewPtStr}`;

  $: muonStr = muon.rate != null
    ? muon.rate.toFixed(0)
    : null;

  $: luxStr = weather?.lux != null
    ? weather.lux.toFixed(0)
    : null;

  // Determine day/night from lux: >10 lux = day
  $: weatherHealth = $healthStore.data?.local?.weather;
  $: weatherLastTs = weather?.ts ?? weatherHealth?.last_event_ts ?? null;
  $: weatherLevel = (weatherLastTs != null && weatherHealth?.staleness_threshold_sec)
    ? deriveStaleness(ageSeconds(weatherLastTs), weatherHealth.staleness_threshold_sec)
    : 'fresh';

  $: maxLuxStr = $maxLuxToday != null
    ? `max today: ${Math.round($maxLuxToday).toLocaleString()} lux`
    : 'max today: —';

  $: luxMeta = (() => {
    if (weather?.lux == null) return `night · ${maxLuxStr}`;
    return weather.lux > 10
      ? maxLuxStr
      : `night · ${maxLuxStr}`;
  })();
</script>

<section class="stats-row" aria-label="Statistics" class:is-stale-amber={weatherLevel === 'amber'} class:is-stale-red={weatherLevel === 'red'}>
  <div class="stat">
    <div class="stat-label">Pressure</div>
    <div class="stat-value">
      {#if pressureStr !== null}
        {pressureStr}
      {:else}
        —
      {/if}
    </div>
    <div class="stat-meta">{pressureMeta}</div>
    {#if weatherLevel !== 'fresh'}
      <StalenessCaption lastTs={weatherLastTs} />
    {/if}
  </div>

  <div class="stat">
    <div class="stat-label">Humidity</div>
    <div class="stat-value">
      {#if humidityStr !== null}
        {humidityStr}<span class="stat-unit">%</span>
      {:else}
        —
      {/if}
    </div>
    <div class="stat-meta">{humidityMeta}</div>
  </div>

  <div class="stat">
    <div class="stat-label">Muons</div>
    <div class="stat-value">
      {#if muonStr !== null}
        {muonStr}
      {:else}
        —
      {/if}
    </div>
    <div class="stat-meta">per minute · pressure corrected</div>
  </div>

  <div class="stat">
    <div class="stat-label">LIGHT</div>
    <div class="stat-value">
      {#if luxStr !== null}
        {luxStr}
      {:else}
        —
      {/if}
    </div>
    <div class="stat-meta">{luxMeta}</div>
  </div>
</section>

<style>
  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    /* token: metric-row-gap (UI-15) — diverges from spec (24px); StatsRow intentionally uses 48px for hero-stat breathing room. Flagged for 08-04 audit footnote. */
    gap: 48px;
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
  }

  @media (max-width: 900px) {
    .stats-row {
      grid-template-columns: 1fr 1fr;
      /* token: metric-row-gap (UI-15) — see desktop divergence note. */
      gap: 48px;
      /* token: section-bottom-margin (UI-15) — 48px mobile-tier matches spec. */
      margin-bottom: 48px;
    }
  }

  @media (max-width: 600px) {
    .stats-row {
      grid-template-columns: 1fr;
      /* token: metric-row-gap (UI-15) — 32px <=600px; further compressed for single-column stack. */
      gap: 32px;
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
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
    /* token: subtitle-bottom-margin (UI-15) — diverges from spec (12px); StatsRow label is a micro-eyebrow, 4px keeps it visually attached to the hero numeral. Flagged for 08-04 audit footnote. */
    margin-bottom: 4px;
  }

  .stat-value {
    font-size: 44px;
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.035em;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }

  .stat-unit {
    font-size: 24px;
    font-weight: 400;
    margin-left: 2px;
  }

  /* token: caption-placement (UI-15) — caption (.stat-meta) is rendered below the hero value, satisfying the spec's "below" placement requirement. */
  .stat-meta {
    font-size: 13px;
    font-weight: 400;
    color: var(--text-muted);
    margin-top: 4px;
  }
</style>
