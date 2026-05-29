<script lang="ts">
  // Stub — Plan 04 implements UI-19 LightChart.
  // Contract: mirrors TemperatureChart.svelte (bootstrap, ResizeObserver,
  // weatherStore subscription, themeStore subscription, StalenessCaption).
</script>
<section class="section" data-testid="light-chart-stub">
  <header class="section-header">
    <div class="eyebrow">LIGHT</div>
    <div class="section-title">Light today</div>
  </header>
  <div class="chart-container"></div>
</section>
<style>
  .section { margin-bottom: 80px; }
  .chart-container { width: 100%; min-height: 180px; }
</style>
