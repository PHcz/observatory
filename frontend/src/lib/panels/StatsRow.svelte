<script lang="ts">
  import { weatherStore, maxLuxToday } from '$lib/stores/weather';
  import { muonDisplayRate } from '$lib/stores/muon';
  import { dewPointC, dewComfort } from '$lib/utils/dewpoint';
  import { tendency } from '$lib/utils/tendency';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import { alertsStore } from '$lib/stores/alerts';
  import { weatherDerivedStore } from '$lib/stores/weatherDerived';

  $: weather = $weatherStore.current;

  $: pressureStr = weather?.pressure_hpa != null
    ? weather.pressure_hpa.toFixed(0)
    : null;

  // Real 3-hour tendency from weather history (was hardcoded "steady").
  // MSLP DISPLAY RULE (UI-SPEC §5b, locked plan revision):
  //   - ALWAYS append MSLP when mslp_hpa != null (reading present).
  //   - mslp_adjusted === true  → no qualifier (real altitude reduction applied)
  //   - mslp_adjusted === false → append "(sea-level adj.)" qualifier
  //   - NEVER suppress the value based on mslp_adjusted or altitude.
  $: mslpSegment = (() => {
    const outlook = $weatherDerivedStore.outlook;
    if (!outlook || outlook.mslp_hpa == null) return '';
    const qualifier = outlook.mslp_adjusted ? '' : ' (sea-level adj.)';
    return ` · MSLP ${Math.round(outlook.mslp_hpa)} hPa${qualifier}`;
  })();

  $: pressureMeta = `hPa · ${
    weather?.pressure_hpa != null && weather?.ts != null
      ? tendency($weatherStore.history, 'pressure_hpa', weather.pressure_hpa, weather.ts, 1.0)
      : 'steady'
  }${mslpSegment}`;

  // Alert dot: visible when there are active alerts. Colour: --alert if any
  // severity==='alert', otherwise --warn. 8px dot, no text, not interactive.
  $: activeAlerts = $alertsStore.active;
  $: hasActiveAlerts = activeAlerts.length > 0;
  $: alertDotClass = (() => {
    if (!hasActiveAlerts) return '';
    return activeAlerts.some((a) => a.severity === 'alert')
      ? 'alert-dot--alert'
      : 'alert-dot--warn';
  })();

  $: humidityStr = weather?.humidity_pct != null
    ? weather.humidity_pct.toFixed(0)
    : null;

  $: dewPtStr = (weather?.temp_c != null && weather?.humidity_pct != null)
    ? `${dewPointC(weather.temp_c, weather.humidity_pct)}°C`
    : '—';

  $: humidityMeta = `${
    weather?.humidity_pct != null && weather?.ts != null
      ? tendency($weatherStore.history, 'humidity_pct', weather.humidity_pct, weather.ts, 5)
      : 'steady'
  } · dew point ${dewPtStr}`;

  $: dewComfortStr = (weather?.temp_c != null && weather?.humidity_pct != null)
    ? dewComfort(dewPointC(weather.temp_c, weather.humidity_pct))
    : null;

  // Server-reconciled, pressure-corrected mean over recent complete minutes —
  // not the lossy client rolling-60s count (which under-counts + flickers).
  $: muonStr = $muonDisplayRate != null
    ? $muonDisplayRate.toFixed(0)
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
    <div class="stat-label-row">
      <span class="stat-label">Pressure</span>
      {#if hasActiveAlerts}
        <span class="alert-dot {alertDotClass}" aria-hidden="true"></span>
      {/if}
    </div>
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
    {#if dewComfortStr}
      <div class="stat-subnote">{dewComfortStr}</div>
    {/if}
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
      /* 2×2 on phone — four full-width stacked hero numbers read as an
         oversized, ragged column; a 2-up grid is balanced and compact. */
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

  /* Wrapper for label + optional alert dot — keeps dot inline with the label text. */
  .stat-label-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
  }

  /* Alert dot: 8px circle, no text, not interactive. Signifies "scroll to WeatherAlertsPanel". */
  .alert-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .alert-dot--warn {
    background: var(--warn);
  }

  .alert-dot--alert {
    background: var(--alert);
  }

  .stat-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
    /* token: subtitle-bottom-margin (UI-15) — diverges from spec (12px); StatsRow label is a micro-eyebrow, 4px keeps it visually attached to the hero numeral. Flagged for 08-04 audit footnote. */
    margin-bottom: 0;
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

  /* Dew-point comfort-band guide — mirrors the HumidityChart caption so the
     reading is interpretable at the stat card too (operator request). */
  .stat-subnote {
    font-size: 11px;
    font-weight: 400;
    color: var(--text-muted);
    margin-top: 4px;
    line-height: 1.4;
  }
</style>
