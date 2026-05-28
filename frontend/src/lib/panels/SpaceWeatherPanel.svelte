<script lang="ts">
  import { spaceWeatherStore } from '$lib/stores/spaceWeather';
  import KpBar from '$lib/atoms/KpBar.svelte';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  $: current = $spaceWeatherStore.current;
  $: kp_index = current?.kp_index ?? null;
  $: solar_wind_kms = current?.solar_wind_kms ?? null;
  $: flare_class = current?.flare_class ?? null;

  $: flareClassMeta = flare_class == null || flare_class < 'M'
    ? 'Last 24h peak · no major activity'
    : 'Last 24h peak';

  $: solarWindMeta = solar_wind_kms != null && solar_wind_kms >= 600
    ? 'km/s · elevated'
    : 'km/s · within normal range';

  $: kpMeta = kp_index != null && kp_index >= 5
    ? 'Active · storm threshold reached'
    : 'Quiet · scale 0–9, storm threshold is 5';

  $: noaa = $healthStore.data?.external?.noaa;
  $: swLastTs = $spaceWeatherStore.current?.ts ?? noaa?.last_event_ts ?? null;
  $: swLevel = swLastTs != null
    ? deriveStaleness(ageSeconds(swLastTs), noaa?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC)
    : 'fresh';
</script>

<section class="space-weather-panel" class:is-stale-amber={swLevel === 'amber'} class:is-stale-red={swLevel === 'red'}>
  <header class="section-header">
    <div class="section-title-row">
      <h2 class="section-title">Space weather</h2>
      <span class="section-meta">NOAA SWPC</span>
    </div>
    <p class="section-sub">Solar activity affects cosmic ray flux. A geomagnetic storm 24–72 hours from now would typically show as a dip in the muon chart above.</p>
    <StalenessCaption lastTs={swLastTs} level={swLevel} />
  </header>

  <div class="solar-cards">
    <div class="solar-card">
      <div class="solar-card-label">Flare class</div>
      <div class="solar-card-value">{flare_class ?? '—'}</div>
      <div class="solar-card-meta">{flareClassMeta}</div>
    </div>

    <div class="solar-card">
      <div class="solar-card-label">Solar wind</div>
      <div class="solar-card-value">{solar_wind_kms != null ? solar_wind_kms.toFixed(0) : '—'}</div>
      <div class="solar-card-meta">{solarWindMeta}</div>
    </div>

    <div class="solar-card">
      <div class="solar-card-label">Kp index</div>
      <div class="solar-card-value">{kp_index != null ? `Kp ${kp_index.toFixed(1)}` : '—'}</div>
      <KpBar kpIndex={kp_index} />
      <div class="solar-card-meta">{kpMeta}</div>
    </div>
  </div>

  {#if kp_index != null && kp_index >= 5}
    <p class="forbush">Geomagnetic disturbance at this level typically causes a Forbush decrease — watch for a dip in the muon chart 24–72 hours from now.</p>
  {/if}
</section>

<style>
  .space-weather-panel {
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
  }

  /* token: subtitle-bottom-margin (UI-15) — diverges from spec (12px) to 32px
     because section-header contains both title-row AND section-sub stacked, and
     the larger gap separates the header block from the solar-card grid below.
     caption-placement: below — StalenessCaption is rendered in template above
     .section-header for this panel; visually flows above the card grid. */
  .section-header {
    margin-bottom: 32px;
  }

  .section-title-row {
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin-bottom: 8px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  .section-meta {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
  }

  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    max-width: 600px;
  }

  .solar-cards {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    /* token: metric-row-gap (UI-15) — diverges from spec (24px) to 32px because
       solar-cards are bordered containers (32px internal padding) and need a
       larger external gap to read as siblings rather than merged. Flagged for
       follow-up. */
    gap: 32px;
  }

  .solar-card {
    padding: 32px;
    border: 1px solid var(--border);
    border-radius: 4px;
  }

  .solar-card-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
    margin-bottom: 12px;
  }

  .solar-card-value {
    font-size: 32px;
    font-weight: 400;
    line-height: 1.0;
    color: var(--text);
    font-variant-numeric: tabular-nums;
    margin-bottom: 8px;
  }

  .solar-card-meta {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 8px;
  }

  .forbush {
    margin-top: 24px;
    font-size: 13px;
    color: var(--text-secondary);
    max-width: 640px;
    line-height: 1.5;
    padding: 16px;
    background: var(--border-soft);
    border-radius: 4px;
  }

  @media (max-width: 900px) {
    .solar-cards {
      grid-template-columns: 1fr;
    }
  }
</style>
