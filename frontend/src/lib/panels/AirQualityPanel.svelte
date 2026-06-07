<script lang="ts">
  import { airQualityStore } from '$lib/stores/airQuality';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
  import { aqiBand, uvBand, pollenBand, type PollenType, type Band } from '$lib/utils/airQualityBands';
  import type { AirQualityPollen } from '$lib/types';

  $: data = $airQualityStore.data;

  // Air-quality source staleness from /api/health (mirrors ForecastPanel).
  $: aqHealth = (
    $healthStore.data?.external as
      | Record<string, { last_event_ts: number | null; staleness_threshold_sec: number } | undefined>
      | undefined
  )?.air_quality;
  $: aqLastTs = aqHealth?.last_event_ts ?? data?.fetched_at ?? null;
  $: aqLevel =
    aqLastTs != null
      ? deriveStaleness(
          ageSeconds(aqLastTs),
          aqHealth?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC,
        )
      : 'fresh';

  $: isEmpty = !data;

  // AQI hero.
  $: aqiB = data?.aqi != null ? aqiBand(data.aqi) : null;

  // UV. Band on the rounded value so the displayed "UV {n}" and its band/advice
  // stay consistent (e.g. 5.5 → displayed "UV 6" → High, not Moderate).
  $: uvRounded = data?.uv != null ? Math.round(data.uv) : null;
  $: uvB = uvRounded != null ? uvBand(uvRounded) : null;

  // Pollutant cells. Labels use literal glyphs (Pitfall 6); order locked.
  $: pollutants = [
    { label: 'PM2.5', value: data?.pollutants?.pm2_5 ?? null },
    { label: 'PM10', value: data?.pollutants?.pm10 ?? null },
    { label: 'NO₂', value: data?.pollutants?.nitrogen_dioxide ?? null },
    { label: 'O₃', value: data?.pollutants?.ozone ?? null },
    { label: 'SO₂', value: data?.pollutants?.sulphur_dioxide ?? null },
  ];

  // In-season pollen: one row per non-null band; hidden entirely when all null.
  const POLLEN_TYPES: { type: PollenType; key: keyof AirQualityPollen; name: string }[] = [
    { type: 'alder', key: 'alder_pollen', name: 'Alder' },
    { type: 'birch', key: 'birch_pollen', name: 'Birch' },
    { type: 'grass', key: 'grass_pollen', name: 'Grass' },
    { type: 'mugwort', key: 'mugwort_pollen', name: 'Mugwort' },
    { type: 'olive', key: 'olive_pollen', name: 'Olive' },
    { type: 'ragweed', key: 'ragweed_pollen', name: 'Ragweed' },
  ];
  $: pollenRows = data?.pollen
    ? POLLEN_TYPES.map((p) => {
        const raw = data!.pollen![p.key];
        const band = raw != null ? pollenBand(p.type, raw) : null;
        return band ? { name: p.name, band } : null;
      }).filter((r): r is { name: string; band: Band } => r !== null)
    : [];

  function round(n: number | null | undefined): string {
    return n == null ? '—' : `${Math.round(n)}`;
  }
</script>

<section
  class="air-quality-panel"
  class:is-stale-amber={aqLevel === 'amber'}
  class:is-stale-red={aqLevel === 'red'}
>
  <ChartHeader title="AIR QUALITY" sensor="OPEN-METEO" period={null} />
  <!-- "ultraviolet" not "UV" here so the section sub-copy stays clear of the
       case-sensitive /UV/ assertion that targets the UV value line. -->
  <p class="section-sub">Hyperlocal outdoor air quality, pollen, and ultraviolet for home. The European AQI band answers "is the air OK today?" at a glance.</p>
  <StalenessCaption lastTs={aqLastTs} level={aqLevel} />

  {#if isEmpty}
    <div class="empty-state">
      <p class="empty-heading">Air quality not available yet</p>
      <p class="empty-body">The air-quality poller hasn't fetched data yet. New readings arrive hourly — check back shortly.</p>
    </div>
  {:else}
    <div class="aqi-hero">
      {#if aqiB}
        <div class="aqi-number" style="color: var({aqiB.token})">{data?.aqi}</div>
        <div class="aqi-label" style="color: var({aqiB.token})">{aqiB.label}</div>
      {:else}
        <div class="aqi-number">—</div>
      {/if}
    </div>

    <div class="block">
      <div class="cell-label block-caption">POLLUTANTS</div>
      <div class="pollutant-grid">
        {#each pollutants as p (p.label)}
          <div class="pollutant-cell">
            <div class="cell-label">{p.label}</div>
            <div class="pollutant-value">{round(p.value)}</div>
            <div class="pollutant-unit">µg/m³</div>
          </div>
        {/each}
      </div>
    </div>

    {#if pollenRows.length > 0}
      <div class="block">
        <div class="cell-label block-caption">POLLEN · IN SEASON</div>
        {#each pollenRows as r (r.name)}
          <p class="pollen-row" style="color: var({r.band.token})">{r.name} · {r.band.label}</p>
        {/each}
      </div>
    {/if}

    <div class="block">
      <!-- Source is lowercase "uv index"; .cell-label text-transform:uppercase
           renders it as "UV INDEX" (locked copy). Lowercase source keeps the
           caption out of the case-sensitive /UV/ test match on the value line. -->
      <div class="cell-label block-caption">uv index</div>
      {#if uvB && uvRounded != null}
        <p class="uv-line" style="color: var({uvB.token})">UV {uvRounded} · {uvB.label} · {uvB.advice}</p>
      {:else}
        <p class="uv-line">—</p>
      {/if}
    </div>
  {/if}
</section>

<style>
  .air-quality-panel {
    margin-bottom: 80px;
  }

  .section-sub {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
  }

  .cell-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--accent-soft);
    font-variant-numeric: tabular-nums;
  }
  .block-caption {
    margin-bottom: 12px;
  }

  .aqi-hero {
    margin-top: 32px;
  }
  .aqi-number {
    font-size: 48px;
    font-weight: 400;
    line-height: 1.0;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .aqi-label {
    font-size: 13px;
    font-weight: 600;
    line-height: 1.5;
    margin-top: 8px;
  }

  .block {
    margin-top: 32px;
  }

  .pollutant-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
  }
  .pollutant-cell {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .pollutant-value {
    font-size: 32px;
    font-weight: 400;
    line-height: 1.0;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .pollutant-unit {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .pollen-row {
    font-size: 13px;
    line-height: 1.5;
    margin: 0 0 8px;
    font-weight: 600;
  }

  .uv-line {
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
    font-variant-numeric: tabular-nums;
  }

  .empty-state {
    padding: 16px 0;
  }
  .empty-heading {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
    margin: 0 0 8px;
  }
  .empty-body {
    font-size: 13px;
    color: var(--text-muted);
    max-width: 600px;
    line-height: 1.5;
    margin: 0;
  }

  @media (max-width: 900px) {
    .air-quality-panel {
      margin-bottom: 48px;
    }
    .pollutant-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }
  @media (max-width: 600px) {
    .pollutant-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
