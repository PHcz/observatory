<script lang="ts">
  import { settingsStore } from '$lib/stores/settings';
  import type { PanelKey } from '$lib/utils/settingsSchema';

  export let panelKey: PanelKey;
  export let label: string;
  export let disabled = false;

  function onToggle(e: Event) {
    const checked = (e.target as HTMLInputElement).checked;
    settingsStore.update((s) => ({
      ...s,
      panels: { ...s.panels, [panelKey]: checked },
    }));
  }
</script>

<label class="switch-row" class:disabled>
  <span class="label">{label}</span>
  <input
    type="checkbox"
    role="switch"
    checked={$settingsStore.panels[panelKey]}
    on:change={onToggle}
    aria-label={`Show ${label} panel`}
    {disabled}
  />
  <span class="switch" aria-hidden="true"></span>
</label>

<style>
  .switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 16px;
    background: var(--bg);
    border-radius: 4px;
    cursor: pointer;
    position: relative;
  }
  .switch-row:hover {
    background: var(--bg-elevated);
  }
  .switch-row.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .label {
    font-size: 13px;
    font-weight: 400;
    color: var(--text);
  }
  input[type='checkbox'] {
    position: absolute;
    opacity: 0;
    width: 40px;
    height: 24px;
    right: 16px;
    top: 16px;
    margin: 0;
    cursor: pointer;
  }
  .switch {
    display: inline-block;
    width: 40px;
    height: 24px;
    background: var(--border);
    border-radius: 12px;
    position: relative;
    transition: background 0.15s;
  }
  .switch::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background: var(--bg);
    border-radius: 50%;
    transition: left 0.15s;
  }
  input:checked ~ .switch {
    background: var(--text);
  }
  input:checked ~ .switch::after {
    left: 18px;
  }
  input:focus-visible ~ .switch {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
</style>
