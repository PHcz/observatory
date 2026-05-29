<script lang="ts">
  import { settingsStore } from '$lib/stores/settings';
  import type { Theme } from '$lib/utils/settingsSchema';

  const OPTIONS: ReadonlyArray<{ value: Theme; label: string; ariaLabel: string }> = [
    { value: 'light', label: 'Light', ariaLabel: 'Light theme' },
    { value: 'dark', label: 'Dark', ariaLabel: 'Dark theme' },
    { value: 'auto', label: 'Auto', ariaLabel: 'Automatic theme (follow system)' },
  ];

  function select(v: Theme) {
    settingsStore.update((s) => ({ ...s, theme: v }));
  }
</script>

<fieldset class="theme-picker" aria-label="Theme">
  <legend class="visually-hidden">Theme</legend>
  {#each OPTIONS as opt}
    <label class="seg" class:selected={$settingsStore.theme === opt.value}>
      <input
        type="radio"
        name="theme"
        value={opt.value}
        checked={$settingsStore.theme === opt.value}
        on:change={() => select(opt.value)}
        aria-label={opt.ariaLabel}
      />
      <span>{opt.label}</span>
    </label>
  {/each}
</fieldset>

<style>
  .theme-picker {
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex;
    margin: 0;
    padding: 0;
    height: 40px;
    background: var(--bg);
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
  .seg {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 13px;
    font-weight: 400;
    color: var(--text);
    position: relative;
  }
  .seg input {
    position: absolute;
    opacity: 0;
    width: 100%;
    height: 100%;
    cursor: pointer;
    margin: 0;
  }
  .seg.selected {
    background: var(--bg-elevated);
    font-weight: 600;
  }
  .seg + .seg {
    border-left: 1px solid var(--border);
  }
  .seg input:focus-visible + span {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
    border-radius: 2px;
  }
</style>
