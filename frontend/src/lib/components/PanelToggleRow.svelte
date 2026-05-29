<script lang="ts">
  import type { PanelKey } from '$lib/utils/settingsSchema';
  export let panelKey: PanelKey;
  export let label: string;
</script>
<div class="panel-toggle-stub" data-testid="panel-toggle-stub" data-panel-key={panelKey}>{label}</div>
