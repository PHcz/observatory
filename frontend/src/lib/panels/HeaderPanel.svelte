<script lang="ts">
  import { onMount } from 'svelte';
  import { weatherStore } from '$lib/stores/weather';
  import { muonStore } from '$lib/stores/muon';
  import { earthquakeStore } from '$lib/stores/earthquakes';
  import { astronomyStore } from '$lib/stores/astronomy';
  import { composeSubtitle } from '$lib/utils/narrative';
  import { tsToLocalTime, ageSeconds } from '$lib/utils/time';
  import { healthStore } from '$lib/stores/health';
  import { deriveStaleness } from '$lib/utils/staleness';
  import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

  // Current local time, updated every minute
  let currentTimeSec = Math.floor(Date.now() / 1000);

  onMount(() => {
    const interval = setInterval(() => {
      currentTimeSec = Math.floor(Date.now() / 1000);
    }, 60_000);
    return () => clearInterval(interval);
  });

  $: tempStr = $weatherStore.current?.temp_c != null
    ? $weatherStore.current.temp_c.toFixed(1)
    : null;

  $: nowSec = currentTimeSec;
  $: hourLocal = new Date(nowSec * 1000).getHours();

  $: bgsList = $earthquakeStore.recent.filter(e => e.source === 'bgs');
  $: bgsLastWeek = bgsList.filter(e => e.ts > nowSec - 7 * 86400 && (e.magnitude ?? 0) < 4.0);
  $: ukSmallQuakeCount = bgsLastWeek.length;
  $: ukMaxMag = bgsList.length > 0
    ? Math.max(0, ...bgsList.map(e => e.magnitude ?? 0))
    : 0;

  $: subtitle = composeSubtitle({
    hourLocal,
    pressureTrendHpaPerHr: null, // TODO: compute from history in a later plan
    muonRate: $muonStore.rate,
    ukSmallQuakeCount,
    ukMaxMag,
  });

  function moonPhaseName(phase: number): string {
    if (phase < 0.03 || phase >= 0.97) return 'New moon';
    if (phase < 0.22) return 'Waxing crescent';
    if (phase < 0.28) return 'First quarter';
    if (phase < 0.47) return 'Waxing gibbous';
    if (phase < 0.53) return 'Full moon';
    if (phase < 0.72) return 'Waning gibbous';
    if (phase < 0.78) return 'Last quarter';
    return 'Waning crescent';
  }

  $: sunriseStr = $astronomyStore
    ? tsToLocalTime($astronomyStore.sunrise_ts)
    : '—';
  $: sunsetStr = $astronomyStore
    ? tsToLocalTime($astronomyStore.sunset_ts)
    : '—';
  $: moonPhaseStr = $astronomyStore
    ? `${moonPhaseName($astronomyStore.moon_phase)} · ${Math.round($astronomyStore.moon_illumination_pct)}% illuminated`
    : '—';

  $: weatherHealth = $healthStore.data?.local?.weather;
  $: weatherLastTs = $weatherStore.current?.ts ?? weatherHealth?.last_event_ts ?? null;
  $: weatherLevel = (weatherLastTs != null && weatherHealth?.staleness_threshold_sec)
    ? deriveStaleness(ageSeconds(weatherLastTs), weatherHealth.staleness_threshold_sec)
    : 'fresh';
</script>

<header class="header" class:is-stale-amber={weatherLevel === 'amber'} class:is-stale-red={weatherLevel === 'red'}>
  <div class="header-main">
    <span class="hero-overline">Outside · Right now</span>
    <h1 class="hero" aria-label="Current outside temperature">
      {#if tempStr !== null}
        {tempStr}<span class="hero-unit">°C</span>
      {:else}
        —
      {/if}
    </h1>
    <p class="subtitle">{subtitle}</p>
    {#if weatherLevel !== 'fresh'}
      <StalenessCaption lastTs={weatherLastTs} />
    {/if}
  </div>

  <aside class="aside">
    <div class="aside-stack">
      <span class="aside-label">Local time</span>
      <span class="aside-value">{tsToLocalTime(nowSec)}</span>
    </div>
    <div class="aside-stack">
      <span class="aside-label">Sun</span>
      <span class="aside-value">Sunrise {sunriseStr} · Sunset {sunsetStr}</span>
    </div>
    <div class="aside-stack">
      <span class="aside-label">Moon</span>
      <span class="aside-value">{moonPhaseStr}</span>
    </div>
  </aside>
</header>

<style>
  .header {
    display: flex;
    align-items: flex-start;
    gap: 64px;
    padding-bottom: 48px;
    margin-bottom: 80px;
    border-bottom: 1px solid var(--border);
  }

  .header-main {
    flex: 1;
    min-width: 0;
  }

  @media (max-width: 900px) {
    .header {
      flex-direction: column;
      gap: 32px;
      margin-bottom: 48px;
      padding-bottom: 32px;
    }
  }

  .hero-overline {
    display: block;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .hero {
    display: block;
    font-size: clamp(96px, 18vw, 180px);
    font-weight: 400;
    line-height: 0.88;
    letter-spacing: -0.065em;
    font-variant-numeric: tabular-nums;
    color: var(--text);
    margin: 0 0 16px 0;
  }

  .hero-unit {
    font-size: 48px;
    font-weight: 400;
    line-height: 0.88;
    letter-spacing: -0.02em;
    vertical-align: baseline;
    margin-left: 4px;
  }

  .subtitle {
    font-size: 16px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--text-secondary);
    margin: 0;
  }

  .aside {
    display: flex;
    flex-direction: column;
    gap: 16px;
    flex-shrink: 0;
    padding-top: 16px;
  }

  .aside-stack {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .aside-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
    margin-bottom: 4px;
  }

  .aside-value {
    font-size: 13px;
    font-weight: 400;
    color: var(--text);
  }
</style>
