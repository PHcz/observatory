<script lang="ts">
  export let source: 'usgs' | 'emsc' | 'bgs';

  const SOURCE_LABEL: Record<string, string> = {
    usgs: 'USGS',
    emsc: 'EMSC',
    bgs: 'BGS',
  };
</script>

<span class="source-badge">{SOURCE_LABEL[source] ?? source.toUpperCase()}</span>

<style>
  .source-badge {
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.20em;
    color: var(--accent-soft);
    text-transform: uppercase;
  }
</style>
