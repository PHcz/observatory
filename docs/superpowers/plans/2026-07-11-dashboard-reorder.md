# Dashboard Section Reorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users reorder dashboard sections via drag-and-drop (and keyboard/buttons) in the settings screen, persisted in local settings.

**Architecture:** Add an `order: PanelKey[]` permutation to the settings schema (with safe-merge). The dashboard renders from a pure `buildRenderPlan(order, panels)` that groups the earthquakes/lightning two-col pair and the indoor stats+charts block. The settings screen reorders that array via a zero-dependency pointer-drag Svelte action plus ↑/↓ buttons and arrow keys.

**Tech Stack:** SvelteKit (Svelte 5 in **legacy mode** — use `export let`, `$:`, `$store`, `<svelte:component>`; do NOT use runes), TypeScript, vitest + `@testing-library/svelte` (tests live in `frontend/tests/unit/`), pointer events (no new runtime dependency).

## Global Constraints

- **No new runtime dependency.** `frontend/package.json` `dependencies` is `{}` and must stay empty. Implement drag with native pointer events only.
- **Svelte legacy idioms only** — `export let`, `$:`, `createEventDispatcher`, `<svelte:component>`. No runes (`$state`/`$props`/`$derived`).
- **Tests go in `frontend/tests/unit/*.test.ts`** (not colocated in `src/`). Run from `frontend/`.
- **`order` is always a full permutation of `ALL_PANELS`** — `mergeOrder` guarantees this; nothing downstream should re-validate.
- All commands run from `frontend/`. Unit runner: `npm run test:unit -- --run [filter]` (one-shot vitest; the bare `npm run test` also triggers Playwright e2e — avoid it in the task loop). Type check: `npm run check` (svelte-check). Build: `npm run build`.
- Commit messages end with the footer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Settings schema — `order` field + `mergeOrder`

**Files:**
- Modify: `frontend/src/lib/utils/settingsSchema.ts`
- Test: `frontend/tests/unit/settingsSchema.test.ts`

**Interfaces:**
- Consumes: existing `PanelKey`, `ALL_PANELS`, `DEFAULTS`, `parseSettings`.
- Produces:
  - `Settings` now has `order: PanelKey[]`.
  - `DEFAULTS.order = [...ALL_PANELS]`.
  - `export function mergeOrder(stored: unknown, canonical: PanelKey[]): PanelKey[]` — always returns a full permutation of `canonical`.
  - `parseSettings` returns `{ theme, panels, order }`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/unit/settingsSchema.test.ts`:

```ts
import { DEFAULTS, parseSettings, ALL_PANELS, mergeOrder } from '$lib/utils/settingsSchema';

describe('mergeOrder', () => {
  it('returns canonical order when stored is not an array', () => {
    expect(mergeOrder(undefined, ALL_PANELS)).toEqual(ALL_PANELS);
    expect(mergeOrder(null, ALL_PANELS)).toEqual(ALL_PANELS);
    expect(mergeOrder('nope', ALL_PANELS)).toEqual(ALL_PANELS);
  });

  it('preserves a valid full permutation', () => {
    const reversed = [...ALL_PANELS].reverse();
    expect(mergeOrder(reversed, ALL_PANELS)).toEqual(reversed);
  });

  it('drops unknown keys', () => {
    const stored = ['lightning', 'bogusPanel', 'headerPanel'];
    const result = mergeOrder(stored, ALL_PANELS);
    expect(result).not.toContain('bogusPanel');
    expect(result[0]).toBe('lightning');
    expect(result[1]).toBe('headerPanel');
  });

  it('appends missing canonical keys in canonical order', () => {
    const stored = ['lightning', 'headerPanel'];
    const result = mergeOrder(stored, ALL_PANELS);
    expect(result).toHaveLength(ALL_PANELS.length);
    expect(new Set(result)).toEqual(new Set(ALL_PANELS));
    expect(result[0]).toBe('lightning');
    expect(result[1]).toBe('headerPanel');
    // remaining are canonical order minus the two already-placed
    expect(result.slice(2)).toEqual(ALL_PANELS.filter((k) => k !== 'lightning' && k !== 'headerPanel'));
  });

  it('collapses duplicates', () => {
    const stored = ['lightning', 'lightning', 'headerPanel'];
    const result = mergeOrder(stored, ALL_PANELS);
    expect(result.filter((k) => k === 'lightning')).toHaveLength(1);
    expect(new Set(result)).toEqual(new Set(ALL_PANELS));
  });
});

describe('parseSettings order', () => {
  it('defaults order to ALL_PANELS when absent', () => {
    expect(parseSettings('{"theme":"dark"}').order).toEqual(ALL_PANELS);
  });

  it('safe-merges a stored partial order', () => {
    const result = parseSettings('{"order":["lightning","headerPanel"]}');
    expect(result.order[0]).toBe('lightning');
    expect(new Set(result.order)).toEqual(new Set(ALL_PANELS));
  });

  it('DEFAULTS.order equals ALL_PANELS', () => {
    expect(DEFAULTS.order).toEqual(ALL_PANELS);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:unit -- --run settingsSchema`
Expected: FAIL — `mergeOrder` is not exported / `order` undefined.

- [ ] **Step 3: Implement the schema changes**

In `frontend/src/lib/utils/settingsSchema.ts`:

Add `order` to the interface:

```ts
export interface Settings {
  theme: Theme;
  panels: Record<PanelKey, boolean>;
  order: PanelKey[];
}
```

Add `order` to `DEFAULTS` (keep the existing `theme` and `panels` fields):

```ts
export const DEFAULTS: Settings = {
  theme: 'auto',
  panels: Object.fromEntries(
    ALL_PANELS.map((k) => [k, !PANEL_DEFAULTS_OFF.includes(k)])
  ) as Record<PanelKey, boolean>,
  order: [...ALL_PANELS],
};
```

Add `mergeOrder` (place above `parseSettings`):

```ts
// Safe-merge a stored order into a full permutation of `canonical`:
// keep valid stored keys in their stored order (de-duped), drop unknown keys,
// then append any canonical keys the stored order was missing. Guarantees the
// result is always a complete permutation — the same missing-key philosophy as
// the panels safe-merge above.
export function mergeOrder(stored: unknown, canonical: PanelKey[]): PanelKey[] {
  const valid = new Set<string>(canonical);
  const seen = new Set<PanelKey>();
  const result: PanelKey[] = [];
  if (Array.isArray(stored)) {
    for (const k of stored) {
      if (typeof k === 'string' && valid.has(k) && !seen.has(k as PanelKey)) {
        result.push(k as PanelKey);
        seen.add(k as PanelKey);
      }
    }
  }
  for (const k of canonical) {
    if (!seen.has(k)) result.push(k);
  }
  return result;
}
```

In `parseSettings`, after building `panels`, add the order and include it in the return object:

```ts
    const order = mergeOrder((parsed as { order?: unknown })?.order, ALL_PANELS);
    return { theme, panels, order };
```

(The `if (!raw)` and `catch` branches already `return structuredClone(DEFAULTS)`, which now includes `order` — leave them.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:unit -- --run settingsSchema`
Expected: PASS (all schema tests, including the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/settingsSchema.ts frontend/tests/unit/settingsSchema.test.ts
git commit -m "feat(settings): add reorderable panel order to schema with safe-merge

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pure helpers — `moveItem` + `buildRenderPlan`

**Files:**
- Create: `frontend/src/lib/utils/renderPlan.ts`
- Test: `frontend/tests/unit/renderPlan.test.ts`

**Interfaces:**
- Consumes: `PanelKey`, `Record<PanelKey, boolean>` from `settingsSchema`.
- Produces:
  - `export type RenderItem = { kind: 'panel'; key: PanelKey } | { kind: 'indoor' } | { kind: 'twocol'; keys: PanelKey[] }`
  - `export function moveItem<T>(list: readonly T[], from: number, to: number): T[]`
  - `export function buildRenderPlan(order: PanelKey[], panels: Record<PanelKey, boolean>): RenderItem[]`

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/unit/renderPlan.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { moveItem, buildRenderPlan, type RenderItem } from '$lib/utils/renderPlan';
import { ALL_PANELS, type PanelKey } from '$lib/utils/settingsSchema';

const allVisible = (): Record<PanelKey, boolean> =>
  Object.fromEntries(ALL_PANELS.map((k) => [k, true])) as Record<PanelKey, boolean>;

describe('moveItem', () => {
  it('moves an item down', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd']);
  });
  it('moves an item up', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 3, 1)).toEqual(['a', 'd', 'b', 'c']);
  });
  it('is a no-op when from === to', () => {
    expect(moveItem(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'b', 'c']);
  });
  it('clamps an out-of-range target', () => {
    expect(moveItem(['a', 'b', 'c'], 0, 99)).toEqual(['b', 'c', 'a']);
  });
  it('returns a copy for an invalid from index', () => {
    expect(moveItem(['a', 'b'], 5, 0)).toEqual(['a', 'b']);
  });
});

describe('buildRenderPlan', () => {
  it('groups adjacent earthquakes + lightning into one twocol item', () => {
    const order = ['earthquakes', 'lightning', 'aurora'] as PanelKey[];
    const plan = buildRenderPlan(order, allVisible());
    expect(plan[0]).toEqual({ kind: 'twocol', keys: ['earthquakes', 'lightning'] });
    expect(plan[1]).toEqual({ kind: 'panel', key: 'aurora' });
  });

  it('pairs them in stored order even if lightning comes first', () => {
    const order = ['lightning', 'earthquakes'] as PanelKey[];
    const plan = buildRenderPlan(order, allVisible());
    expect(plan).toEqual([{ kind: 'twocol', keys: ['lightning', 'earthquakes'] }]);
  });

  it('renders them full-width when separated', () => {
    const order = ['earthquakes', 'aurora', 'lightning'] as PanelKey[];
    const plan = buildRenderPlan(order, allVisible());
    expect(plan).toEqual([
      { kind: 'panel', key: 'earthquakes' },
      { kind: 'panel', key: 'aurora' },
      { kind: 'panel', key: 'lightning' },
    ]);
  });

  it('renders the survivor full-width when one of the pair is hidden', () => {
    const panels = allVisible();
    panels.lightning = false;
    const plan = buildRenderPlan(['earthquakes', 'lightning'] as PanelKey[], panels);
    expect(plan).toEqual([{ kind: 'panel', key: 'earthquakes' }]);
  });

  it('emits a single indoor item for indoorAir', () => {
    const plan = buildRenderPlan(['indoorAir'] as PanelKey[], allVisible());
    expect(plan).toEqual([{ kind: 'indoor' }]);
  });

  it('omits hidden panels', () => {
    const panels = allVisible();
    panels.aurora = false;
    const plan = buildRenderPlan(['aurora', 'healthRow'] as PanelKey[], panels);
    expect(plan).toEqual([{ kind: 'panel', key: 'healthRow' }]);
  });

  it('respects order', () => {
    const plan = buildRenderPlan(['healthRow', 'headerPanel'] as PanelKey[], allVisible());
    expect(plan).toEqual([
      { kind: 'panel', key: 'healthRow' },
      { kind: 'panel', key: 'headerPanel' },
    ]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:unit -- --run renderPlan`
Expected: FAIL — module `renderPlan` not found.

- [ ] **Step 3: Implement the helpers**

Create `frontend/src/lib/utils/renderPlan.ts`:

```ts
import type { PanelKey } from './settingsSchema';

export type RenderItem =
  | { kind: 'panel'; key: PanelKey }
  | { kind: 'indoor' }
  | { kind: 'twocol'; keys: PanelKey[] };

// Immutable array move with a clamped target index. `from` out of range → copy.
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  const result = list.slice();
  if (from < 0 || from >= result.length) return result;
  const target = Math.max(0, Math.min(to, result.length - 1));
  const [item] = result.splice(from, 1);
  result.splice(target, 0, item);
  return result;
}

const PAIR: ReadonlySet<PanelKey> = new Set(['earthquakes', 'lightning']);

// Turn an ordered panel list + visibility map into a render plan. Only visible
// panels appear. earthquakes+lightning fuse into a two-col block when adjacent;
// indoorAir becomes one 'indoor' block (stats row + charts, rendered together).
export function buildRenderPlan(
  order: PanelKey[],
  panels: Record<PanelKey, boolean>,
): RenderItem[] {
  const visible = order.filter((k) => panels[k]);
  const plan: RenderItem[] = [];
  for (let i = 0; i < visible.length; i++) {
    const key = visible[i];
    if (key === 'indoorAir') {
      plan.push({ kind: 'indoor' });
      continue;
    }
    if (PAIR.has(key)) {
      const next = visible[i + 1];
      if (next !== undefined && PAIR.has(next) && next !== key) {
        plan.push({ kind: 'twocol', keys: [key, next] });
        i++; // consume the paired panel
        continue;
      }
    }
    plan.push({ kind: 'panel', key });
  }
  return plan;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test:unit -- --run renderPlan`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/renderPlan.ts frontend/tests/unit/renderPlan.test.ts
git commit -m "feat(dashboard): add moveItem + buildRenderPlan helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Panel component registry

**Files:**
- Create: `frontend/src/lib/panels/registry.ts`
- Test: `frontend/tests/unit/registry.test.ts`

**Interfaces:**
- Produces: `export const PANEL_COMPONENTS: Partial<Record<PanelKey, ComponentType>>` — one entry per 1:1 panel. `indoorAir` is intentionally **absent** (rendered specially by the dashboard).

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/registry.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { PANEL_COMPONENTS } from '$lib/panels/registry';
import { ALL_PANELS } from '$lib/utils/settingsSchema';

describe('PANEL_COMPONENTS registry', () => {
  it('has a component for every panel except indoorAir', () => {
    for (const key of ALL_PANELS) {
      if (key === 'indoorAir') {
        expect(PANEL_COMPONENTS[key]).toBeUndefined();
      } else {
        expect(PANEL_COMPONENTS[key]).toBeTruthy();
      }
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- --run registry`
Expected: FAIL — module `registry` not found.

- [ ] **Step 3: Implement the registry**

Create `frontend/src/lib/panels/registry.ts`:

```ts
import type { ComponentType } from 'svelte';
import type { PanelKey } from '$lib/utils/settingsSchema';
import HeaderPanel from './HeaderPanel.svelte';
import StatsRow from './StatsRow.svelte';
import TodayStrip from './TodayStrip.svelte';
import ZambrettiCard from './ZambrettiCard.svelte';
import WeatherAlertsPanel from './WeatherAlertsPanel.svelte';
import ForecastPanel from './ForecastPanel.svelte';
import AirQualityPanel from './AirQualityPanel.svelte';
import MuonChart from './MuonChart.svelte';
import MuonDiagnosticsPanel from './MuonDiagnosticsPanel.svelte';
import MuonGainDriftPanel from './MuonGainDriftPanel.svelte';
import AdcSpectrumPanel from './AdcSpectrumPanel.svelte';
import BarometricPanel from './BarometricPanel.svelte';
import NmdbOverlayPanel from './NmdbOverlayPanel.svelte';
import ForbushPanel from './ForbushPanel.svelte';
import SpaceWeatherPanel from './SpaceWeatherPanel.svelte';
import EarthquakeList from './EarthquakeList.svelte';
import LightningPanel from './LightningPanel.svelte';
import AuroraPanel from './AuroraPanel.svelte';
import TemperatureChart from './TemperatureChart.svelte';
import PressureChart from './PressureChart.svelte';
import HumidityChart from './HumidityChart.svelte';
import LightChart from './LightChart.svelte';
import HealthRow from './HealthRow.svelte';

// One entry per 1:1 panel. `indoorAir` is intentionally absent — the dashboard
// renders IndoorStatsRow + IndoorCharts together for that key (see renderPlan
// 'indoor' item). earthquakes/lightning ARE here (their side-by-side grouping is
// the plan's job, but each is a normal component).
export const PANEL_COMPONENTS: Partial<Record<PanelKey, ComponentType>> = {
  headerPanel: HeaderPanel,
  statsRow: StatsRow,
  todayStrip: TodayStrip,
  zambrettiCard: ZambrettiCard,
  weatherAlerts: WeatherAlertsPanel,
  forecast: ForecastPanel,
  airQuality: AirQualityPanel,
  muonChart: MuonChart,
  muonDiagnostics: MuonDiagnosticsPanel,
  muonGainDrift: MuonGainDriftPanel,
  adcSpectrum: AdcSpectrumPanel,
  barometric: BarometricPanel,
  nmdbOverlay: NmdbOverlayPanel,
  forbush: ForbushPanel,
  spaceWeather: SpaceWeatherPanel,
  earthquakes: EarthquakeList,
  lightning: LightningPanel,
  aurora: AuroraPanel,
  temperatureChart: TemperatureChart,
  pressureChart: PressureChart,
  humidityChart: HumidityChart,
  lightChart: LightChart,
  healthRow: HealthRow,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test:unit -- --run registry`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/panels/registry.ts frontend/tests/unit/registry.test.ts
git commit -m "feat(dashboard): add panel component registry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Render the dashboard from the plan

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `PANEL_COMPONENTS` (Task 3), `buildRenderPlan` (Task 2), `IndoorStatsRow`, `IndoorCharts`, `settingsStore`.
- Produces: dashboard renders in `$settingsStore.order`, honoring visibility and grouping. No new exports.

**Verification:** rendering the full page in jsdom triggers WebSocket/poller init (network), so this task is verified by the Task 2/3 unit tests plus a **manual browser check**, not a new unit test.

- [ ] **Step 1: Rewrite the render body**

In `frontend/src/routes/+page.svelte`:

Replace the panel component imports (the block importing `HeaderPanel` through `HealthRow`, lines ~18-42) with just the registry, the plan builder, and the two indoor components (which the plan references by kind, not via the registry). Keep `Container` and `CadenceWarningBanner` imports:

```svelte
  import { PANEL_COMPONENTS } from '$lib/panels/registry';
  import { buildRenderPlan } from '$lib/utils/renderPlan';
  import IndoorStatsRow from '$lib/panels/IndoorStatsRow.svelte';
  import IndoorCharts from '$lib/panels/IndoorCharts.svelte';
```

Leave the entire `<script>` store-init/cleanup section (`onMount`/`onDestroy` and all the `cleanup*` / `init*Polling` wiring) exactly as-is — every store must keep initialising regardless of order or visibility.

Add the reactive plan at the end of the `<script>` block:

```svelte
  $: plan = buildRenderPlan($settingsStore.order, $settingsStore.panels);
```

Replace the entire markup body between `<CadenceWarningBanner />` and the `<footer class="dashboard-footer">` (the whole hardcoded `{#if $settingsStore.panels.*}` sequence including the `two-col` block) with:

```svelte
  {#each plan as item (item.kind === 'twocol' ? `twocol:${item.keys.join('+')}` : item.kind === 'indoor' ? 'indoor' : `panel:${item.key}`)}
    {#if item.kind === 'indoor'}
      <IndoorStatsRow />
      <IndoorCharts />
    {:else if item.kind === 'twocol'}
      <div class="two-col">
        {#each item.keys as k (k)}
          {@const TwoColComp = PANEL_COMPONENTS[k]}
          {#if TwoColComp}<svelte:component this={TwoColComp} />{/if}
        {/each}
      </div>
    {:else}
      {@const PanelComp = PANEL_COMPONENTS[item.key]}
      {#if PanelComp}<svelte:component this={PanelComp} />{/if}
    {/if}
  {/each}
```

Keep the `<footer>`, `<style>` (including `.two-col`) unchanged.

- [ ] **Step 2: Type-check and build**

Run: `npm run check && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 3: Run the full unit suite (guard against regressions)**

Run: `npm run test:unit -- --run`
Expected: PASS (existing + Tasks 1-3).

- [ ] **Step 4: Manual browser verification**

Start the dev server via the preview tool (`.claude/launch.json` "frontend" config; proxies `/api` + `/ws` to `observatory.local`). Load `http://localhost:5173/`. Confirm:
- All previously-visible sections still render, in the default order.
- Earthquakes + Lightning are side-by-side.
- Indoor stats row + indoor charts now render together (charts moved up under the stats row — the expected default-layout change).
- No console errors (`read_console_messages`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(dashboard): render sections from the ordered render plan

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Settings reorder row (grip + ↑/↓ + arrow keys)

**Files:**
- Create: `frontend/src/lib/components/PanelReorderRow.svelte`
- Modify: `frontend/src/routes/settings/+page.svelte`
- Test: `frontend/tests/unit/PanelReorderRow.test.ts`
- Test: `frontend/tests/unit/settingsReorder.test.ts`

**Interfaces:**
- `PanelReorderRow` props: `panelKey: PanelKey`, `label: string`, `index: number`, `count: number`, `reorder: (from: number, to: number) => void`.
  - Renders a grip handle (`data-reorder-handle`), the label, ↑/↓ buttons (disabled at bounds), and the visibility switch (same behaviour as the old `PanelToggleRow` — toggles `settingsStore.panels[panelKey]`).
  - Buttons and ArrowUp/ArrowDown (on the grip) call `reorder(index, index-1|index+1)`.
  - Root element carries `data-reorder-item` and `data-index={index}` (consumed by the drag action in Task 6).
- Settings page owns `reorder(from, to)` — updates `settingsStore.order` via `moveItem` and sets an `aria-live` announcement.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/unit/PanelReorderRow.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import PanelReorderRow from '$lib/components/PanelReorderRow.svelte';
import { settingsStore } from '$lib/stores/settings';

const props = (over = {}) => ({
  panelKey: 'lightning' as const,
  label: 'Lightning',
  index: 2,
  count: 5,
  reorder: vi.fn(),
  ...over,
});

describe('PanelReorderRow', () => {
  beforeEach(() => settingsStore.resetToDefaults());

  it('renders a grip handle and the label', () => {
    const { container, getByText } = render(PanelReorderRow, { props: props() });
    expect(container.querySelector('[data-reorder-handle]')).not.toBeNull();
    expect(getByText('Lightning')).toBeInTheDocument();
  });

  it('root carries data-reorder-item and data-index', () => {
    const { container } = render(PanelReorderRow, { props: props({ index: 3 }) });
    const root = container.querySelector('[data-reorder-item]') as HTMLElement;
    expect(root).not.toBeNull();
    expect(root.getAttribute('data-index')).toBe('3');
  });

  it('up button calls reorder(index, index-1)', async () => {
    const reorder = vi.fn();
    const { getByLabelText } = render(PanelReorderRow, { props: props({ index: 2, reorder }) });
    await fireEvent.click(getByLabelText('Move Lightning up'));
    expect(reorder).toHaveBeenCalledWith(2, 1);
  });

  it('down button calls reorder(index, index+1)', async () => {
    const reorder = vi.fn();
    const { getByLabelText } = render(PanelReorderRow, { props: props({ index: 2, reorder }) });
    await fireEvent.click(getByLabelText('Move Lightning down'));
    expect(reorder).toHaveBeenCalledWith(2, 3);
  });

  it('disables up at the first row and down at the last row', () => {
    const first = render(PanelReorderRow, { props: props({ index: 0, count: 5 }) });
    expect((first.getByLabelText('Move Lightning up') as HTMLButtonElement).disabled).toBe(true);
    const last = render(PanelReorderRow, { props: props({ index: 4, count: 5 }) });
    expect((last.getByLabelText('Move Lightning down') as HTMLButtonElement).disabled).toBe(true);
  });

  it('ArrowUp on the grip calls reorder(index, index-1)', async () => {
    const reorder = vi.fn();
    const { container } = render(PanelReorderRow, { props: props({ index: 2, reorder }) });
    const grip = container.querySelector('[data-reorder-handle]') as HTMLElement;
    await fireEvent.keyDown(grip, { key: 'ArrowUp' });
    expect(reorder).toHaveBeenCalledWith(2, 1);
  });

  it('the visibility switch still toggles settingsStore.panels[panelKey]', async () => {
    const { container } = render(PanelReorderRow, { props: props() });
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(input.checked).toBe(true);
    await fireEvent.click(input);
    expect(get(settingsStore).panels.lightning).toBe(false);
  });
});
```

Create `frontend/tests/unit/settingsReorder.test.ts` (page-level wiring — no network):

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import SettingsPage from '../../src/routes/settings/+page.svelte';
import { settingsStore } from '$lib/stores/settings';
import { ALL_PANELS } from '$lib/utils/settingsSchema';

describe('settings reorder wiring', () => {
  beforeEach(() => settingsStore.resetToDefaults());

  it('clicking the second row up-button swaps the first two panels in order', async () => {
    const { getAllByLabelText } = render(SettingsPage);
    const before = get(settingsStore).order;
    // Second row corresponds to ALL_PANELS[1]; its "up" moves it to index 0.
    const upButtons = getAllByLabelText(/Move .* up/);
    await fireEvent.click(upButtons[1]);
    const after = get(settingsStore).order;
    expect(after[0]).toBe(before[1]);
    expect(after[1]).toBe(before[0]);
    expect(new Set(after)).toEqual(new Set(ALL_PANELS));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:unit -- --run PanelReorderRow settingsReorder`
Expected: FAIL — `PanelReorderRow` module not found.

- [ ] **Step 3: Create `PanelReorderRow.svelte`**

Create `frontend/src/lib/components/PanelReorderRow.svelte`:

```svelte
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
```

- [ ] **Step 4: Wire the settings page**

In `frontend/src/routes/settings/+page.svelte`:

Replace the `PanelToggleRow` import with:

```svelte
  import PanelReorderRow from '$lib/components/PanelReorderRow.svelte';
  import { moveItem } from '$lib/utils/renderPlan';
```

Replace the `PANEL_LABELS` array with a keyed record (same labels):

```ts
  const PANEL_LABELS: Record<PanelKey, string> = {
    headerPanel: 'Header',
    statsRow: 'Stats',
    todayStrip: 'Today so far (daily summary strip)',
    zambrettiCard: 'Near-term outlook (Zambretti)',
    weatherAlerts: 'Weather alerts (frost & pressure-fall rules)',
    forecast: 'Local forecast',
    airQuality: 'Air quality',
    indoorAir: 'Indoor air (CO₂)',
    muonChart: 'Muon flux chart',
    muonDiagnostics: 'Muon diagnostics (inter-arrival + rate distribution)',
    muonGainDrift: 'Muon gain-drift (weekly MIP-peak tracking)',
    adcSpectrum: 'ADC spectrum',
    barometric: 'Barometric coefficient',
    nmdbOverlay: 'Cosmic ray overlay',
    forbush: 'Forbush indicator',
    spaceWeather: 'Space weather',
    earthquakes: 'Earthquakes',
    lightning: 'Lightning',
    aurora: 'Aurora',
    temperatureChart: 'Temperature chart',
    pressureChart: 'Pressure chart',
    humidityChart: 'Humidity chart',
    lightChart: 'Light chart',
    healthRow: 'System health',
  };

  let announcement = '';

  function reorder(from: number, to: number) {
    settingsStore.update((s) => ({ ...s, order: moveItem(s.order, from, to) }));
    const order = $settingsStore.order;
    announcement = `Moved ${PANEL_LABELS[order[to]]} to position ${to + 1} of ${order.length}`;
  }
```

Replace the panels `.toggle-stack` block:

```svelte
    <div class="toggle-stack">
      {#each $settingsStore.order as key, i (key)}
        <PanelReorderRow
          panelKey={key}
          label={PANEL_LABELS[key]}
          index={i}
          count={$settingsStore.order.length}
          {reorder}
        />
      {/each}
    </div>
    <p class="sr-only" aria-live="polite">{announcement}</p>
```

Add an `.sr-only` style inside the page `<style>`:

```css
  .sr-only {
    position: absolute;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
```

- [ ] **Step 5: Delete the superseded toggle row**

`PanelToggleRow` is only imported by the settings page (now replaced). Remove it and its test:

```bash
git rm frontend/src/lib/components/PanelToggleRow.svelte frontend/tests/unit/PanelToggleRow.test.ts
```

- [ ] **Step 6: Run tests + type-check**

Run: `npm run test:unit -- --run PanelReorderRow settingsReorder && npm run check`
Expected: PASS; no type errors. Then `npm run test:unit -- --run` (full unit suite) — PASS (no lingering `PanelToggleRow` references).

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/lib/components/PanelReorderRow.svelte frontend/src/routes/settings/+page.svelte frontend/tests/unit/PanelReorderRow.test.ts frontend/tests/unit/settingsReorder.test.ts
git commit -m "feat(settings): reorderable panel rows with buttons + arrow keys

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Pointer-drag action (mouse + touch)

**Files:**
- Create: `frontend/src/lib/actions/reorderable.ts`
- Modify: `frontend/src/routes/settings/+page.svelte`

**Interfaces:**
- `export function reorderable(node: HTMLElement, params: { onReorder: (from: number, to: number) => void }): { update(p): void; destroy(): void }`
  - Delegates `pointerdown` from any `[data-reorder-handle]`; reads the row via its closest `[data-reorder-item]` and `data-index`; on drop calls `onReorder(from, to)`.

**Verification:** pointer-drag physics are DOM/gesture-driven; verified by **manual browser check**, not a unit test.

- [ ] **Step 1: Implement the action**

Create `frontend/src/lib/actions/reorderable.ts`:

```ts
// Zero-dependency pointer-drag reordering for a vertical list. Rows carry
// [data-reorder-item] + data-index; drag handles carry [data-reorder-handle].
// Unified mouse + touch via Pointer Events. Commits once, on pointerup.
interface Params {
  onReorder: (from: number, to: number) => void;
}

export function reorderable(node: HTMLElement, params: Params) {
  let onReorder = params.onReorder;
  let fromIndex = -1;
  let items: HTMLElement[] = [];
  let dragRow: HTMLElement | null = null;
  let overRow: HTMLElement | null = null;

  const rowFor = (el: EventTarget | null): HTMLElement | null =>
    el instanceof Element ? (el.closest('[data-reorder-item]') as HTMLElement | null) : null;

  function clearMarks() {
    for (const it of items) {
      it.classList.remove('reorder-over-before', 'reorder-over-after');
    }
  }

  function targetIndexFor(clientY: number): number {
    // Insert before the first row whose vertical midpoint is below the pointer;
    // otherwise append after the last row.
    for (let i = 0; i < items.length; i++) {
      const r = items[i].getBoundingClientRect();
      if (clientY < r.top + r.height / 2) return i;
    }
    return items.length;
  }

  function onPointerMove(e: PointerEvent) {
    if (fromIndex < 0) return;
    e.preventDefault();
    let target = targetIndexFor(e.clientY);
    clearMarks();
    // Show an insertion line. target === items.length → after the last row.
    const markIdx = Math.min(target, items.length - 1);
    overRow = items[markIdx] ?? null;
    if (overRow) {
      overRow.classList.add(target > markIdx ? 'reorder-over-after' : 'reorder-over-before');
    }
  }

  function onPointerUp(e: PointerEvent) {
    if (fromIndex < 0) return;
    let target = targetIndexFor(e.clientY);
    // Removing the dragged row before re-inserting shifts later targets down by one.
    if (target > fromIndex) target -= 1;
    clearMarks();
    dragRow?.classList.remove('reorder-dragging');
    const from = fromIndex;
    fromIndex = -1;
    dragRow = null;
    overRow = null;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerUp);
    if (target !== from && target >= 0) onReorder(from, target);
  }

  function onPointerDown(e: PointerEvent) {
    const handle = (e.target as Element).closest('[data-reorder-handle]');
    if (!handle) return;
    const row = rowFor(e.target);
    if (!row) return;
    e.preventDefault();
    items = Array.from(node.querySelectorAll<HTMLElement>('[data-reorder-item]'));
    fromIndex = items.indexOf(row);
    dragRow = row;
    row.classList.add('reorder-dragging');
    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
  }

  node.addEventListener('pointerdown', onPointerDown);

  return {
    update(p: Params) {
      onReorder = p.onReorder;
    },
    destroy() {
      node.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
    },
  };
}
```

- [ ] **Step 2: Apply the action + drag styles in the settings page**

In `frontend/src/routes/settings/+page.svelte`:

Import the action:

```svelte
  import { reorderable } from '$lib/actions/reorderable';
```

Add `use:reorderable` to the list container:

```svelte
    <div class="toggle-stack" use:reorderable={{ onReorder: reorder }}>
```

Add drag-feedback styles (these target classes the action toggles on the rows) to the page `<style>`:

```css
  .toggle-stack :global(.reorder-dragging) {
    opacity: 0.5;
  }
  .toggle-stack :global(.reorder-over-before) {
    box-shadow: inset 0 2px 0 0 var(--accent);
  }
  .toggle-stack :global(.reorder-over-after) {
    box-shadow: inset 0 -2px 0 0 var(--accent);
  }
```

- [ ] **Step 3: Type-check + build**

Run: `npm run check && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: Manual browser verification**

In the preview at `http://localhost:5173/settings`:
- Drag a row by its grip (mouse) → insertion line follows, drops into the new position, dashboard order updates on return.
- Emulate touch (`resize_window` mobile preset) → drag works, page doesn't scroll while dragging the handle.
- ↑/↓ buttons and arrow keys still reorder.
- Toggle a switch → visibility still works, independent of order.
- Reset to defaults → order and visibility both reset.
- Check both light and dark themes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/actions/reorderable.ts frontend/src/routes/settings/+page.svelte
git commit -m "feat(settings): pointer drag-and-drop reordering (mouse + touch)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Final verification & deploy note

**Files:** none (verification only).

- [ ] **Step 1: Full suite + type-check + build**

Run: `npm run test:unit -- --run && npm run check && npm run build`
Expected: all tests PASS, no type errors, build succeeds.

- [ ] **Step 2: End-to-end manual pass**

In the preview: set a custom order (drag + buttons + keys), reload the page, confirm the order **persists** (localStorage), confirm the dashboard reflects it, confirm earthquakes/lightning fuse only when adjacent, confirm the indoor block moves as one. Both themes.

- [ ] **Step 3: Deploy (optional, user-confirmed)**

The frontend deploys separately from git. When the user approves:

```bash
cd frontend && npm run build
OBS_SSH_TARGET=ph@observatory.local scripts/deploy-frontend.sh
```

Then verify at `http://observatory.local:8000/`. (Backend untouched — no obs-api restart or migration needed.)

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## Self-review notes

- **Spec coverage:** data model + `mergeOrder` (Task 1); `buildRenderPlan`/`moveItem` (Task 2); registry (Task 3); dashboard render + smart grouping + indoor block (Task 4); reorder UI with buttons/keys + a11y aria-live (Task 5); zero-dep pointer drag mouse+touch (Task 6); persistence + reset + verification (Tasks 5-7). All spec sections mapped.
- **Grouping edge cases** (adjacent pair, separated, one hidden, indoor) are covered by `buildRenderPlan` tests in Task 2.
- **Type consistency:** `reorder(from, to)` signature is identical across `PanelReorderRow` prop, settings page, and the action's `onReorder`. `moveItem`/`buildRenderPlan`/`PANEL_COMPONENTS`/`mergeOrder` names match their definitions.
- **No new dependency** — pointer events only; `package.json` `dependencies` stays `{}`.
