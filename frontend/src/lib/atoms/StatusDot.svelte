<script lang="ts">
  export let status: 'green' | 'yellow' | 'amber' | 'red' = 'green';
</script>

<span class="status-dot status-{status}" aria-label={status}></span>

<style>
  .status-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .status-green  { background: var(--accent); }
  .status-yellow { background: #e8c878; }
  .status-amber  { background: var(--warn); }
  .status-red    { background: var(--alert); }
</style>
