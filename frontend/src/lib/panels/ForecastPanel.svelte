<script lang="ts">
  import { forecastStore } from '$lib/stores/forecast';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import WeatherGlyph from '$lib/atoms/WeatherGlyph.svelte';
  import { condition } from '$lib/utils/weatherCodes';
  import type { ForecastTempMetric } from '$lib/types';

  $: data = $forecastStore.data;

  // Forecast source staleness from /api/health (mirrors SpaceWeatherPanel).
  // The `forecast` source appears once the poller + freshness registration
  // exist (10-03); until then the cast keeps svelte-check happy.
  $: forecastHealth = ($healthStore.data?.external as Record<string, { last_event_ts: number | null; staleness_threshold_sec: number } | undefined> | undefined)?.forecast;
  $: fcLastTs = forecastHealth?.last_event_ts ?? data?.fetched_at ?? null;
  $: fcLevel = fcLastTs != null
    ? deriveStaleness(ageSeconds(fcLastTs), forecastHealth?.staleness_threshold_sec ?? DEFAULT_STALENESS_THRESHOLD_SEC)
    : 'fresh';

  $: hourly = data?.hourly ?? [];
  $: daily = data?.daily ?? [];
  $: isEmpty = !data || (hourly.length === 0 && daily.length === 0);

  // vs-actual: the 10-03 router nests temp as {high, low, actual}; the Wave-0
  // RED test feeds a flat {forecast, actual, delta, label}. Normalise to a list
  // of temp metrics the template renders identically.
  $: vsa = data?.vs_actual ?? null;
  $: tempMetrics = ((): ForecastTempMetric[] => {
    if (!vsa) return [];
    const t = vsa.temp as unknown as Record<string, unknown>;
    if (t && (t.high || t.low)) {
      return [t.high as ForecastTempMetric, t.low as ForecastTempMetric].filter(Boolean);
    }
    if (t && ('forecast' in t || 'actual' in t)) {
      return [t as unknown as ForecastTempMetric];
    }
    return [];
  })();

  function hh(ts: number): string {
    const d = new Date(ts * 1000);
    return `${String(d.getHours()).padStart(2, '0')}:00`;
  }
  function weekday(ts: number): string {
    return new Date(ts * 1000).toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase();
  }
  function round(n: number | null | undefined): string {
    return n == null ? '—' : `${Math.round(n)}°`;
  }

  // "Forecast 18° / actual 16° — running 2° cool" (UI-SPEC copy strings).
  function tempSentence(m: ForecastTempMetric): string {
    const f = m.forecast == null ? '—' : `${Math.round(m.forecast)}°`;
    if (m.actual == null) {
      return `Forecast ${f} (no measured value yet)`;
    }
    const a = `${Math.round(m.actual)}°`;
    if (m.label === 'on_track' || m.delta == null) {
      return `Forecast ${f} / actual ${a} — on track`;
    }
    const mag = Math.abs(Math.round(m.delta));
    return `Forecast ${f} / actual ${a} — running ${mag}° ${m.label}`;
  }
</script>

<section
  class="forecast-panel"
  class:is-stale-amber={fcLevel === 'amber'}
  class:is-stale-red={fcLevel === 'red'}
>
  <header class="section-header">
    <div class="section-title-row">
      <h2 class="section-title">Local forecast</h2>
      <span class="section-meta">OPEN-METEO</span>
    </div>
    <p class="section-sub">Hourly outlook for the next 24 hours and a 7-day view for home. Forecast-vs-actual below compares today's outlook against what the outside sensor measured.</p>
    <StalenessCaption lastTs={fcLastTs} level={fcLevel} />
  </header>

  {#if isEmpty}
    <div class="empty-state">
      <p class="empty-heading">Forecast not available yet</p>
      <p class="empty-body">The forecast poller hasn't fetched data yet. New readings arrive hourly — check back shortly.</p>
    </div>
  {:else}
    {#if hourly.length > 0}
      <div class="block">
        <div class="cell-label block-caption">NEXT 24 HOURS</div>
        <div class="strip">
          {#each hourly as h (h.ts)}
            <div class="hour-cell">
              <div class="cell-label">{hh(h.ts)}</div>
              <div class="glyph"><WeatherGlyph code={h.weather_code} /></div>
              <div class="temp">{round(h.temp_c)}</div>
              {#if h.precip_prob_pct != null}
                <div class="precip">{h.precip_prob_pct}%</div>
              {/if}
              <div class="cond">{condition(h.weather_code).label}</div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if daily.length > 0}
      <div class="block daily-block">
        <div class="cell-label block-caption">7-DAY OUTLOOK</div>
        <div class="daily-row">
          {#each daily as d (d.ts)}
            <div class="day-cell">
              <div class="cell-label">{weekday(d.ts)}</div>
              <div class="glyph"><WeatherGlyph code={d.weather_code} /></div>
              <div class="hilo">
                <span class="hi">{round(d.temp_max_c)}</span>
                <span class="lo">{round(d.temp_min_c)}</span>
              </div>
              {#if d.precip_prob_max_pct != null}
                <div class="precip">{d.precip_prob_max_pct}%</div>
              {/if}
              <div class="cond">{condition(d.weather_code).label}</div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if vsa}
      <div class="vs-actual">
        <div class="cell-label block-caption">FORECAST VS ACTUAL</div>
        {#each tempMetrics as m}
          <p class="vs-line" class:warn={m.warn}>{tempSentence(m)}</p>
        {/each}
        {#if vsa.humidity}
          <p class="vs-line">
            {#if vsa.humidity.actual != null}
              Forecast {vsa.humidity.forecast}% / actual {vsa.humidity.actual}% humidity
            {:else}
              Forecast {vsa.humidity.forecast}% humidity (no measured value yet)
            {/if}
          </p>
        {/if}
        {#if vsa.pressure}
          <p class="vs-line">
            {#if vsa.pressure.actual != null}
              Forecast {vsa.pressure.forecast} hPa / actual {vsa.pressure.actual} hPa
            {:else}
              Forecast {vsa.pressure.forecast} hPa (no measured value yet)
            {/if}
          </p>
        {/if}
        {#if vsa.precip}
          <p class="vs-line precip-info">{vsa.precip.prob_max}% chance of precipitation today</p>
        {/if}
      </div>
    {/if}
  {/if}
</section>

<style>
  .forecast-panel {
    margin-bottom: 80px;
  }

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

  .daily-block {
    margin-top: 24px;
  }

  .strip {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .hour-cell {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-width: 56px;
  }

  .daily-row {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 12px;
  }
  .day-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .glyph {
    color: var(--accent);
    line-height: 0;
  }

  .temp {
    font-size: 16px;
    font-weight: 400;
    line-height: 1.0;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .hilo {
    font-size: 16px;
    font-weight: 400;
    line-height: 1.0;
    font-variant-numeric: tabular-nums;
    display: flex;
    gap: 6px;
  }
  .hi { color: var(--text); }
  .lo { color: var(--text-muted); }

  .precip {
    font-size: 12px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
  .cond {
    font-size: 12px;
    color: var(--text-muted);
    text-align: center;
    line-height: 1.4;
  }

  .vs-actual {
    margin-top: 32px;
  }
  .vs-line {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
    margin: 0 0 8px;
    font-variant-numeric: tabular-nums;
  }
  .vs-line.warn {
    color: var(--warn);
  }
  .precip-info {
    color: var(--text-muted);
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
    .forecast-panel {
      margin-bottom: 48px;
    }
    .daily-row {
      grid-template-columns: repeat(4, 1fr);
      gap: 12px 8px;
    }
  }
  @media (max-width: 600px) {
    .daily-row {
      grid-template-columns: repeat(3, 1fr);
    }
  }
</style>
