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
  import MoonPhase from '$lib/atoms/MoonPhase.svelte';
  import { feelsLikeC } from '$lib/utils/heatIndex';

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

  function moonTime(ts: number | null | undefined): string {
    return ts != null ? tsToLocalTime(ts) : '—';
  }
  $: moonRiseSetStr = $astronomyStore
    ? `Rise ${moonTime($astronomyStore.moonrise_ts)} · Set ${moonTime($astronomyStore.moonset_ts)}`
    : '—';

  $: weatherHealth = $healthStore.data?.local?.weather;
  $: weatherLastTs = $weatherStore.current?.ts ?? weatherHealth?.last_event_ts ?? null;
  $: weatherLevel = (weatherLastTs != null && weatherHealth?.staleness_threshold_sec)
    ? deriveStaleness(ageSeconds(weatherLastTs), weatherHealth.staleness_threshold_sec)
    : 'fresh';

  // Feels-like (heat index): show only when temp_c > 0 and both values are present.
  // Wind chill not shown — no wind sensor. (UI-SPEC §5a, RESEARCH Pattern 7)
  $: feelsLikeStr = (() => {
    const temp = $weatherStore.current?.temp_c;
    const hum = $weatherStore.current?.humidity_pct;
    if (temp == null || hum == null || temp <= 0) return null;
    return `${Math.round(feelsLikeC(temp, hum))}°C`;
  })();
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
    {#if feelsLikeStr !== null}
      <p class="feels-like">Feels like {feelsLikeStr}</p>
    {/if}
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
      <div class="moon-row">
        {#if $astronomyStore}
          <MoonPhase
            phase={$astronomyStore.moon_phase}
            illuminationPct={$astronomyStore.moon_illumination_pct}
            phaseName={moonPhaseName($astronomyStore.moon_phase)}
            size={78}
          />
        {/if}
        <div class="moon-text">
          <span class="aside-value">{moonPhaseStr}</span>
          <span class="aside-value">{moonRiseSetStr}</span>
        </div>
      </div>
    </div>
  </aside>
</header>

<style>
  .header {
    display: flex;
    align-items: flex-start;
    gap: 64px;
    padding-bottom: 48px;
    /* token: section-bottom-margin (UI-15) */
    margin-bottom: 80px;
    border-bottom: 1px solid var(--border);
  }

  .header-main {
    flex: 1;
    min-width: 0;
  }

  /* Portrait phones/tablets: stack hero over the aside. Scoped to portrait so a
     phone in LANDSCAPE keeps the side-by-side row below (which fills the width
     instead of leaving the right half empty). */
  @media (max-width: 900px) and (orientation: portrait) {
    .header {
      flex-direction: column;
      gap: 32px;
      /* token: section-bottom-margin (UI-15) — 48px tier at ≤900px */
      margin-bottom: 48px;
      padding-bottom: 32px;
    }
  }

  /* Landscape phones (short viewport): keep hero + aside side-by-side so the
     aside occupies the right half rather than collapsing to a left column with
     a large empty gap. max-height:500px targets phones, not landscape tablets. */
  @media (orientation: landscape) and (max-height: 500px) {
    .header {
      flex-direction: row;
      gap: 32px;
      align-items: flex-start;
      /* match the ≤900px spacing tier */
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

  /* Feels-like sub-line: 14px --text-muted, between hero numeral and subtitle.
     Only rendered when temp_c > 0 and humidity_pct present (UI-SPEC §5a). */
  .feels-like {
    font-size: 14px;
    font-weight: 400;
    line-height: 1.5;
    color: var(--text-muted);
    margin: 0 0 8px 0;
  }

  /* token: subtitle-bottom-margin (UI-15) — narrative subtitle is the last element
     in the header-main flow; section-bottom-margin (80px) on .header provides the
     gap to the next sibling. caption-placement: below (StalenessCaption is
     intentionally absent in HeaderPanel — hero number can't carry stale state). */
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

  .moon-row {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .moon-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  /* Portrait phones: put the moon disc beside its text so the block fills the
     row width (stacked disc-above-text left a large empty gap on the right).
     Desktop and landscape keep the disc-above-text layout. */
  @media (max-width: 900px) and (orientation: portrait) {
    .moon-row {
      flex-direction: row;
      align-items: center;
      gap: 16px;
    }
  }
</style>
