<script lang="ts">
  import { spaceWeatherStore } from '#lib/stores/spaceWeather.js';
  import KpBar from '#lib/atoms/KpBar.svelte';
  import { healthStore } from '#lib/stores/health.js';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '#lib/utils/staleness.js';
  import { ageSeconds } from '#lib/utils/time.js';
  import StalenessCaption from '#lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '#lib/atoms/ChartHeader.svelte';

  $: current = $spaceWeatherStore.current;
  $: kp_index = current?.kp_index ?? null;
  $: solar_wind_kms = current?.solar_wind_kms ?? null;
  $: flare_class = current?.flare_class ?? null;
  $: density = current?.solar_wind_density ?? null;
  $: bz = current?.imf_bz_nt ?? null;
  $: bt = current?.imf_bt_nt ?? null;
  $: protons = current?.proton_flux_10mev ?? null;
  $: scaleR = current?.noaa_scale_r ?? null;
  $: scaleS = current?.noaa_scale_s ?? null;
  $: scaleG = current?.noaa_scale_g ?? null;
  $: hasScales = scaleR != null && scaleS != null && scaleG != null;

  // Sustained southward (negative) Bz is what lets the solar wind couple into
  // Earth's field; around −5 nT and below it starts to matter for aurora.
  $: bzText = bz == null ? '—' : `${bz < 0 ? '−' : '+'}${Math.abs(bz).toFixed(1)} nT`;
  $: bzMeta = bz == null
    ? 'Interplanetary magnetic field'
    : bz <= -5
      ? `southward · favours aurora${bt != null ? ` · Bt ${bt.toFixed(1)} nT` : ''}`
      : bz < 0
        ? `southward · weak${bt != null ? ` · Bt ${bt.toFixed(1)} nT` : ''}`
        : `northward · quiet${bt != null ? ` · Bt ${bt.toFixed(1)} nT` : ''}`;

  // ≥10 MeV integral flux defines NOAA's S scale: 10 pfu is S1.
  $: protonText = protons == null
    ? '—'
    : `${protons >= 10 ? protons.toFixed(1) : protons.toPrecision(2)} pfu`;
  $: protonMeta = protons != null && protons >= 10
    ? '≥10 MeV · radiation storm level (S1+)'
    : '≥10 MeV · background level';

  const SCALE_NAMES = { R: 'radio blackout', S: 'radiation storm', G: 'geomagnetic storm' } as const;
  $: scalesText = hasScales ? `R${scaleR} · S${scaleS} · G${scaleG}` : '—';
  $: activeScales = hasScales
    ? ([['R', scaleR], ['S', scaleS], ['G', scaleG]] as const)
        .filter(([, level]) => (level ?? 0) > 0)
        .map(([key, level]) => `${key}${level} ${SCALE_NAMES[key]}`)
    : [];
  $: scalesMeta = !hasScales
    ? 'NOAA scales · 0–5'
    : activeScales.length > 0
      ? activeScales.join(' · ')
      : 'No storms or blackouts in progress';

  $: flareClassMeta = flare_class == null || flare_class < 'M'
    ? 'Last 24h peak · no major activity'
    : 'Last 24h peak';

  $: solarWindMeta = `km/s${density != null ? ` · ${density.toFixed(1)} p/cm³` : ''} · ${
    solar_wind_kms != null && solar_wind_kms >= 600 ? 'elevated' : 'within normal range'
  }`;

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
  <ChartHeader title="SPACE WEATHER" sensor="NOAA SWPC" period={null} />
  <p class="section-sub">Solar activity affects cosmic ray flux. A geomagnetic storm 24–72 hours from now would typically show as a dip in the muon chart above.</p>
  <StalenessCaption lastTs={swLastTs} level={swLevel} />

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

    <div class="solar-card">
      <div class="solar-card-label">IMF Bz</div>
      <div class="solar-card-value">{bzText}</div>
      <div class="solar-card-meta">{bzMeta}</div>
    </div>

    <div class="solar-card">
      <div class="solar-card-label">Proton flux</div>
      <div class="solar-card-value">{protonText}</div>
      <div class="solar-card-meta">{protonMeta}</div>
    </div>

    <div class="solar-card">
      <div class="solar-card-label">NOAA scales</div>
      <div class="solar-card-value">{scalesText}</div>
      <div class="solar-card-meta">{scalesMeta}</div>
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

  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
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
