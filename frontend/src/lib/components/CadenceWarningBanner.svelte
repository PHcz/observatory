<script lang="ts">
  import { healthStore } from '$lib/stores/health';

  // NOTE: sessionStorage matches the operator-stated "does not survive reload" behavior from
  // 08-CONTEXT.md §UI-20 (which mis-named the API as localStorage). VALIDATION.md §Manual-Only
  // confirms: "banner re-appears on page reload while drift persists" — sessionStorage delivers
  // exactly that. The banner triggers only for LOCAL sources (weather, muon) where the operator
  // can physically act; external pollers' cadence_warning surfaces in HealthRow dot only
  // (RESEARCH §Open Q 2).
  const BANNER_SOURCES = ['weather', 'muon'] as const;
  type BannerSource = (typeof BANNER_SOURCES)[number];

  const SOURCE_LABELS: Record<BannerSource, string> = {
    weather: 'WEATHER NODE',
    muon: 'MUON DETECTOR',
  };

  function readDismissed(): Set<string> {
    if (typeof sessionStorage === 'undefined') return new Set();
    const out = new Set<string>();
    for (const s of BANNER_SOURCES) {
      if (sessionStorage.getItem(`cadence-dismissed-${s}`) === '1') out.add(s);
    }
    return out;
  }

  let dismissed = readDismissed();

  function explanation(src: BannerSource, ageMin: number): string {
    if (src === 'weather') {
      return `Weather node hasn't published for ${ageMin} min — battery may be low. Check on-device LED.`;
    }
    return `Muon detector hasn't reported for ${ageMin} min — check USB connection and journal.`;
  }

  interface BannerEntry {
    source: BannerSource;
    label: string;
    ageMinutes: number;
    text: string;
  }

  $: warnings = ((): BannerEntry[] => {
    const local = $healthStore.data?.local;
    if (!local) return [];
    const nowSec = Math.floor(Date.now() / 1000);
    const out: BannerEntry[] = [];
    for (const src of BANNER_SOURCES) {
      const entry = (local as Record<string, { cadence_warning?: boolean; last_event_ts: number | null }>)[src];
      if (!entry) continue;
      if (!entry.cadence_warning) {
        // Auto-clear the dismiss state when the condition resolves so the
        // next time it fires the banner re-appears (per VALIDATION.md).
        if (typeof sessionStorage !== 'undefined') {
          sessionStorage.removeItem(`cadence-dismissed-${src}`);
        }
        if (dismissed.has(src)) {
          dismissed = new Set([...dismissed].filter((s) => s !== src));
        }
        continue;
      }
      if (dismissed.has(src)) continue;
      const ageMinutes =
        entry.last_event_ts != null ? Math.max(0, Math.floor((nowSec - entry.last_event_ts) / 60)) : 0;
      out.push({
        source: src,
        label: SOURCE_LABELS[src],
        ageMinutes,
        text: explanation(src, ageMinutes),
      });
    }
    return out;
  })();

  function handleDismiss(src: BannerSource): void {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(`cadence-dismissed-${src}`, '1');
    }
    dismissed = new Set([...dismissed, src]);
  }
</script>

{#each warnings as w (w.source)}
  <div class="banner" role="alert">
    <span class="dot" aria-hidden="true"></span>
    <strong class="label">{w.label}</strong>
    <span class="text">{w.text}</span>
    <button class="dismiss" type="button" on:click={() => handleDismiss(w.source)}>Dismiss</button>
  </div>
{/each}

<style>
  .banner {
    background: #f4e8c8; /* Hyborg warm amber */
    border: 1px solid #c2a868;
    color: #3a2e10;
    padding: 16px 20px;
    margin-bottom: 24px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 18px;
    line-height: 1.4;
  }
  .dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #c2a868;
    flex-shrink: 0;
  }
  .label {
    font-weight: 700;
    letter-spacing: 0.04em;
    font-size: 22px;
  }
  .text {
    flex: 1;
    font-size: 18px;
  }
  .dismiss {
    background: transparent;
    border: 1px solid #c2a868;
    color: #3a2e10;
    padding: 6px 14px;
    cursor: pointer;
    font: inherit;
    border-radius: 3px;
  }
  .dismiss:hover {
    background: #ead9a8;
  }
  @media (max-width: 600px) {
    .banner {
      flex-wrap: wrap;
      padding: 12px 14px;
      font-size: 16px;
    }
    .label {
      font-size: 18px;
    }
    .text {
      font-size: 14px;
      flex-basis: 100%;
    }
  }
</style>
