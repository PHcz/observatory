<script lang="ts">
  import { settingsStore } from '$lib/stores/settings';
  import type { PanelKey } from '$lib/utils/settingsSchema';

  export let panelKey: PanelKey;
  export let label: string;
  export let index: number;
  export let count: number;
  export let reorder: (from: number, to: number) => void;

  $: isFirst = index === 0;
  $: isLast = index === count - 1;

  function moveUp() {
    if (!isFirst) reorder(index, index - 1);
  }
  function moveDown() {
    if (!isLast) reorder(index, index + 1);
  }
  function onGripKeydown(e: KeyboardEvent) {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      moveUp();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveDown();
    }
  }
  function onToggle(e: Event) {
    const checked = (e.target as HTMLInputElement).checked;
    settingsStore.update((s) => ({ ...s, panels: { ...s.panels, [panelKey]: checked } }));
  }
</script>

<div class="reorder-row" data-reorder-item data-index={index}>
  <button
    type="button"
    class="grip"
    data-reorder-handle
    aria-label={`Reorder ${label} (use arrow keys)`}
    on:keydown={onGripKeydown}
  >⠿</button>

  <span class="label">{label}</span>

  <span class="move-btns">
    <button type="button" class="move" aria-label={`Move ${label} up`} disabled={isFirst} on:click={moveUp}>↑</button>
    <button type="button" class="move" aria-label={`Move ${label} down`} disabled={isLast} on:click={moveDown}>↓</button>
  </span>

  <label class="switch-wrap">
    <input
      type="checkbox"
      role="switch"
      checked={$settingsStore.panels[panelKey]}
      on:change={onToggle}
      aria-label={`Show ${label} panel`}
    />
    <span class="switch" aria-hidden="true"></span>
  </label>
</div>

<style>
  .reorder-row {
    display: flex;
    align-items: center;
    gap: 12px;
    height: 56px;
    padding: 0 16px;
    background: var(--bg);
    border-radius: 4px;
  }
  .reorder-row:hover { background: var(--bg-elevated); }
  .grip {
    cursor: grab;
    touch-action: none; /* let the pointer-drag action own touch gestures */
    background: none;
    border: 0;
    color: var(--text-muted);
    font-size: 18px;
    line-height: 1;
    padding: 4px;
    border-radius: 4px;
  }
  .grip:active { cursor: grabbing; }
  .grip:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .label {
    flex: 1;
    font-size: 13px;
    font-weight: 400;
    color: var(--text);
  }
  .move-btns { display: inline-flex; gap: 4px; }
  .move {
    background: none;
    border: 1px solid var(--border);
    color: var(--text);
    width: 28px;
    height: 28px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
  }
  .move:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .move:disabled { opacity: 0.3; cursor: not-allowed; }
  .move:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .switch-wrap { position: relative; display: inline-flex; cursor: pointer; }
  input[type='checkbox'] {
    position: absolute;
    opacity: 0;
    width: 40px;
    height: 24px;
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
    pointer-events: none;
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
  input:checked ~ .switch { background: var(--text); }
  input:checked ~ .switch::after { left: 18px; }
  input:focus-visible ~ .switch { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
