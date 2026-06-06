<script lang="ts">
  // Photoreal moon-phase disc: a real lunar photograph (NASA/LRO, public domain
  // — see static/CREDITS.txt) clipped to a circle, with the unlit region painted
  // over it using an astronomically-shaped terminator (see utils/moonGeometry).
  import { moonShadowPath } from '$lib/utils/moonGeometry';

  export let phase: number;            // normalised 0=new, 0.5=full
  export let illuminationPct: number;  // 0–100
  export let phaseName: string = 'Moon';
  export let size: number = 56;

  $: R = size / 2;
  $: shadow = moonShadowPath(phase, R, R, R);
  $: label = `${phaseName}, ${Math.round(illuminationPct)}% illuminated`;
  // Terminator softening scales with the disc so it reads natural at any size.
  $: blur = Math.max(0.4, size * 0.012);
</script>

<svg
  class="moon"
  width={size}
  height={size}
  viewBox="0 0 {size} {size}"
  role="img"
  aria-label={label}
>
  <defs>
    <clipPath id="moon-disc">
      <circle cx={R} cy={R} r={R} />
    </clipPath>
    <filter id="moon-term-blur" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation={blur} />
    </filter>
  </defs>

  <g clip-path="url(#moon-disc)">
    <image
      href="/moon.jpg"
      x="0"
      y="0"
      width={size}
      height={size}
      preserveAspectRatio="xMidYMid slice"
    />
    <path d={shadow} class="shadow" filter="url(#moon-term-blur)" />
  </g>

  <!-- crisp rim so the grey disc separates from the near-white background -->
  <circle cx={R} cy={R} r={R - 0.5} class="rim" fill="none" />
</svg>

<style>
  .moon {
    display: block;
    flex-shrink: 0;
  }
  .shadow {
    /* deep night-slate, slightly translucent so a ghost of the unlit limb
       survives (earthshine feel) rather than a flat black cut-out */
    fill: #0a0d15;
    opacity: 0.9;
  }
  .rim {
    stroke: var(--border);
    stroke-width: 1;
  }
</style>
