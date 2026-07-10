<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fetchIndoorHistory } from '$lib/api/rest';
  import {
    buildIndoorCo2Plot,
    buildTempPlot,
    buildPressurePlot,
    buildHumidityDewpointPlot,
  } from '$lib/charts/plotHelpers';
  import type { IndoorPoint, WeatherPoint } from '$lib/types';
  import { indoorStore } from '$lib/stores/indoor';
  import ChartHeader from '$lib/atoms/ChartHeader.svelte';

  let co2El: HTMLDivElement | undefined;
  let tempEl: HTMLDivElement | undefined;
  let humEl: HTMLDivElement | undefined;
  let presEl: HTMLDivElement | undefined;
  let observers: ResizeObserver[] = [];
  let timer: ReturnType<typeof setInterval> | undefined;
  let history: IndoorPoint[] = [];

  $: roomLabel = ($indoorStore.current?.nodes?.[0]?.node_id ?? 'indoor').replace(/-/g, ' ').toUpperCase();

  // Reuse the weather chart builders for the shared metrics (temp/humidity/pressure).
  const asWeather = (rows: IndoorPoint[]): WeatherPoint[] =>
    rows.map((r) => ({
      ts: r.ts,
      temp_c: r.temp_c,
      humidity_pct: r.humidity_pct,
      pressure_hpa: r.pressure_hpa,
      lux: null,
    }));

  function renderAll() {
    const w = asWeather(history);
    if (co2El) {
      co2El.innerHTML = '';
      co2El.appendChild(buildIndoorCo2Plot(history, co2El.clientWidth || 600));
    }
    if (tempEl) {
      tempEl.innerHTML = '';
      tempEl.appendChild(buildTempPlot(w, tempEl.clientWidth || 600));
    }
    if (humEl) {
      humEl.innerHTML = '';
      humEl.appendChild(buildHumidityDewpointPlot(w, humEl.clientWidth || 600));
    }
    if (presEl) {
      presEl.innerHTML = '';
      presEl.appendChild(buildPressurePlot(w, presEl.clientWidth || 600));
    }
  }

  async function bootstrap() {
    try {
      history = (await fetchIndoorHistory(24)).rows;
      renderAll();
    } catch {
      /* leave empty — charts render empty axes */
    }
  }

  onMount(() => {
    bootstrap();
    timer = setInterval(bootstrap, 60_000);
    if (typeof ResizeObserver !== 'undefined') {
      for (const el of [co2El, tempEl, humEl, presEl]) {
        if (el) {
          const o = new ResizeObserver(renderAll);
          o.observe(el);
          observers.push(o);
        }
      }
    }
  });

  onDestroy(() => {
    observers.forEach((o) => o.disconnect());
    if (timer) clearInterval(timer);
  });
</script>

<section class="section">
  <ChartHeader title="INDOOR CO₂" sensor={roomLabel} />
  <p class="section-subtitle">
    Carbon dioxide (ppm). Fresh below 800 · air the room above 1000 · ventilate above 1200.
  </p>
  <div bind:this={co2El} data-chart="indoor-co2" class="chart-container"></div>
</section>

<section class="section">
  <ChartHeader title="INDOOR TEMPERATURE" sensor={roomLabel} />
  <p class="section-subtitle">Indoor air temperature from the SCD-41 sensor.</p>
  <div bind:this={tempEl} data-chart="indoor-temp" class="chart-container"></div>
</section>

<section class="section">
  <ChartHeader title="INDOOR HUMIDITY" sensor={roomLabel} />
  <p class="section-subtitle">Relative humidity (solid) and dew point (sage).</p>
  <div bind:this={humEl} data-chart="indoor-humidity" class="chart-container"></div>
</section>

<section class="section">
  <ChartHeader title="INDOOR PRESSURE" sensor={roomLabel} />
  <p class="section-subtitle">Indoor barometric pressure (hPa).</p>
  <div bind:this={presEl} data-chart="indoor-pressure" class="chart-container"></div>
</section>

<style>
  .section {
    margin-bottom: 80px;
  }
  .section-subtitle {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0 0 24px;
  }
  .chart-container {
    width: 100%;
    min-height: 180px;
  }
</style>
