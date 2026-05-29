<script lang="ts">
  // Stub — Plan 04 implements UI-19 PressureChart.
  // Contract: mirrors TemperatureChart.svelte (bootstrap, ResizeObserver,
  // weatherStore subscription, themeStore subscription, StalenessCaption).
</script>
<section class="section" data-testid="pressure-chart-stub">
  <header class="section-header">
    <div class="eyebrow">PRESSURE</div>
    <div class="section-title">Pressure today</div>
  </header>
  <div class="chart-container"></div>
</section>
<style>
  .section { margin-bottom: 80px; }
  .chart-container { width: 100%; min-height: 180px; }
</style>
