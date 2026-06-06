<script lang="ts">
  import { forecastStore } from '$lib/stores/forecast';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness, DEFAULT_STALENESS_THRESHOLD_SEC } from '$lib/utils/staleness';
  import { ageSeconds } from '$lib/utils/time';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';
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

  // Each vs-actual line: a label ("High"/"Low"/"Humidity"/"Pressure"), a
  // "forecast X / actual Y (verdict)" body, and a warn flag. No em dashes.
  type VsLine = { label: string; body: string; warn: boolean };

  function tempBody(m: ForecastTempMetric): { body: string; warn: boolean } {
    const f = m.forecast == null ? '—' : `${Math.round(m.forecast)}°`;
    if (m.actual == null) return { body: `forecast ${f} (no reading yet)`, warn: false };
    const a = `${Math.round(m.actual)}°`;
    const verdict =
      m.label === 'on_track' || m.delta == null
        ? 'on track'
        : `${Math.abs(Math.round(m.delta))}° ${m.label === 'warm' ? 'warmer' : 'cooler'}`;
    return { body: `forecast ${f} / actual ${a} (${verdict})`, warn: !!m.warn };
  }

  // Humidity (%) / pressure (hPa) line with a verdict, mirroring the temp lines.
  function cmpBody(
    f: number | null | undefined,
    a: number | null | undefined,
    unit: string,
    decimals: number,
    band: number,
  ): string {
    if (f == null) return '—';
    const fmt = (n: number): string => (decimals ? n.toFixed(decimals) : `${Math.round(n)}`);
    const ff = `${fmt(f)}${unit}`;
    if (a == null) return `forecast ${ff} (no reading yet)`;
    const aa = `${fmt(a)}${unit}`;
    const d = a - f;
    const verdict =
      Math.abs(d) < band ? 'on track' : `${fmt(Math.abs(d))}${unit} ${d > 0 ? 'higher' : 'lower'}`;
    return `forecast ${ff} / actual ${aa} (${verdict})`;
  }

  $: vsLines = ((): VsLine[] => {
    if (!vsa) return [];
    const out: VsLine[] = [];
    if (tempMetrics[0]) out.push({ label: 'High', ...tempBody(tempMetrics[0]) });
    if (tempMetrics[1]) out.push({ label: 'Low', ...tempBody(tempMetrics[1]) });
    if (vsa.humidity) {
      out.push({
        label: 'Humidity',
        body: cmpBody(vsa.humidity.forecast, vsa.humidity.actual, '%', 0, 5),
        warn: false,
      });
    }
    if (vsa.pressure) {
      out.push({
        label: 'Pressure',
        body: cmpBody(vsa.pressure.forecast, vsa.pressure.actual, ' hPa', 1, 1),
        warn: false,
      });
    }
    return out;
  })();
</script>

<section
  class="forecast-panel"
  class:is-stale-amber={fcLevel === 'amber'}
  class:is-stale-red={fcLevel === 'red'}
>
  <ChartHeader title="LOCAL FORECAST" sensor="OPEN-METEO" period={null} />
  <p class="section-sub">Hourly outlook for the next 24 hours and a 7-day view for home. Forecast-vs-actual below compares today's outlook against what the outside sensor measured.</p>
  <StalenessCaption lastTs={fcLastTs} level={fcLevel} />

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
        {#each vsLines as l}
          <p class="vs-line" class:warn={l.warn}>
            <span class="vs-label">{l.label}</span><span class="vs-body">{l.body}</span>
          </p>
        {/each}
      </div>
    {/if}
  {/if}
</section>

<style>
  .forecast-panel {
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
  /* Line label (High/Low/Humidity/Pressure) — sage, stays accent even on warn
     lines; the body span inherits .vs-line colour (incl. the warn tint). */
  .vs-label {
    color: var(--accent-soft);
    font-weight: 600;
    margin-right: 8px;
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
