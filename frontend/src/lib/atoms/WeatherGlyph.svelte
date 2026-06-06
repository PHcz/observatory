<script lang="ts">
  import { condition } from '$lib/utils/weatherCodes';

  export let code: number | null = null;

  // Resolve the glyph family from the WMO code. The cell wrapping this glyph
  // sets `color: var(--accent)`, so stroke="currentColor" adapts light/dark for
  // free (UI-SPEC §Glyph contract + 10-RESEARCH Pitfall 7). aria-hidden — the
  // adjacent text label carries meaning.
  $: g = condition(code).glyph;
</script>

<svg
  viewBox="0 0 24 24"
  width="24"
  height="24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.5"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#if g === 'sun'}
    <circle cx="12" cy="12" r="4" />
    <line x1="12" y1="2" x2="12" y2="5" />
    <line x1="12" y1="19" x2="12" y2="22" />
    <line x1="2" y1="12" x2="5" y2="12" />
    <line x1="19" y1="12" x2="22" y2="12" />
    <line x1="5" y1="5" x2="7" y2="7" />
    <line x1="17" y1="17" x2="19" y2="19" />
    <line x1="19" y1="5" x2="17" y2="7" />
    <line x1="7" y1="17" x2="5" y2="19" />
  {:else if g === 'sun-cloud'}
    <circle cx="8" cy="8" r="3" />
    <line x1="8" y1="2" x2="8" y2="3.5" />
    <line x1="2.5" y1="8" x2="4" y2="8" />
    <line x1="4.2" y1="4.2" x2="5.2" y2="5.2" />
    <path d="M8 18h8a3 3 0 0 0 0-6 4 4 0 0 0-7.6-1A3 3 0 0 0 8 18z" />
  {:else if g === 'cloud'}
    <path d="M7 18h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 18z" />
  {:else if g === 'fog'}
    <path d="M7 14h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 14z" />
    <line x1="5" y1="18" x2="19" y2="18" />
    <line x1="7" y1="21" x2="17" y2="21" />
  {:else if g === 'drizzle'}
    <path d="M7 14h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 14z" />
    <line x1="9" y1="18" x2="9" y2="20" />
    <line x1="13" y1="18" x2="13" y2="20" />
    <line x1="17" y1="18" x2="17" y2="20" />
  {:else if g === 'rain'}
    <path d="M7 14h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 14z" />
    <line x1="9" y1="17" x2="7.5" y2="21" />
    <line x1="13" y1="17" x2="11.5" y2="21" />
    <line x1="17" y1="17" x2="15.5" y2="21" />
  {:else if g === 'snow'}
    <path d="M7 14h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 14z" />
    <line x1="9" y1="18" x2="9" y2="21" />
    <line x1="7.7" y1="18.8" x2="10.3" y2="20.2" />
    <line x1="10.3" y1="18.8" x2="7.7" y2="20.2" />
    <line x1="15" y1="18" x2="15" y2="21" />
    <line x1="13.7" y1="18.8" x2="16.3" y2="20.2" />
    <line x1="16.3" y1="18.8" x2="13.7" y2="20.2" />
  {:else if g === 'storm'}
    <path d="M7 14h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 14z" />
    <path d="M13 16l-3 4h3l-2 3" />
  {:else}
    <!-- unknown family -> cloud fallback -->
    <path d="M7 18h10a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.6-1.4A3.5 3.5 0 0 0 7 18z" />
  {/if}
</svg>
