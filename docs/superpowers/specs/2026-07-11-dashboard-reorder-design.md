# Dashboard section reorder (drag & drop) — design

**Date:** 2026-07-11
**Status:** Approved (design), pending implementation plan
**Area:** frontend (SvelteKit dashboard + settings)

## Problem

The dashboard renders its ~24 sections in a **hardcoded order** — a fixed
sequence of `{#if $settingsStore.panels.X}<Panel/>{/if}` blocks in
`frontend/src/routes/+page.svelte`. Settings persists only **visibility**
(`panels: Record<PanelKey, boolean>`), not order. Users want to reorder sections
to suit how they read the dashboard, via drag-and-drop in the settings screen.

## Decisions (locked)

1. **Interaction:** custom **pointer-based drag** (unified mouse + touch), plus
   **↑/↓ buttons and arrow keys** as the keyboard/touch-friendly accessible
   fallback. **No new runtime dependency** — the frontend currently has zero
   runtime deps and ships as a static local-first bundle; keep it that way.
2. **Grouped sections — smart defaults:**
   - `earthquakes` + `lightning` render **side-by-side** (two-column) when they
     are **adjacent** in the order and both visible; otherwise each renders
     full-width. Preserves today's look by default, degrades gracefully.
   - `indoorAir` becomes **one movable block** — its stats row and its charts
     render **together** at a single ordered slot.

## UX

The existing **Settings → PANELS** list is the reorder surface. Each row:

```
[⠿ grip]  Label ......................... [↑] [↓]  ( switch )
```

- **Grip handle** (left): press-and-drag to reorder (mouse or touch).
- **↑/↓ buttons** + **arrow keys** (when a row is focused): move the row one
  slot. This is the accessible path and the touch fallback.
- **Visibility toggle** (right): unchanged behaviour.

Order and visibility are **independent**. Hidden panels still appear in the
settings list (so they can be reordered); they simply don't render on the
dashboard. "Reset to defaults" restores both default visibility **and** default
order.

## Data model & migration

Extend `Settings` in `frontend/src/lib/utils/settingsSchema.ts`:

```ts
export interface Settings {
  theme: Theme;
  panels: Record<PanelKey, boolean>;
  order: PanelKey[]; // a permutation of ALL_PANELS
}

export const DEFAULTS: Settings = {
  theme: 'auto',
  panels: /* unchanged */,
  order: [...ALL_PANELS],
};
```

`parseSettings` gains **safe-merge** for `order`, matching the existing
missing-key philosophy. A pure helper:

```ts
export function mergeOrder(stored: unknown, canonical: PanelKey[]): PanelKey[]
```

Rules:
- Not an array / missing → return `[...canonical]`.
- Keep stored keys that are valid `PanelKey`s, **in stored order**, de-duplicated.
- **Drop** entries not in `canonical` (unknown/legacy keys).
- **Append** any `canonical` keys missing from the result, in canonical order
  (so a newly-added panel in a future release shows up even in a customised
  order).

This guarantees the result is always a full permutation of `ALL_PANELS`.

`localStorage` key (`observatory.settings.v1`) and the debounced-write store are
unchanged. `resetToDefaults()` already deep-clones `DEFAULTS`, so it picks up the
default order for free.

## Dashboard rendering

Replace the hardcoded `{#if}` sequence in `+page.svelte` with a data-driven
render plan.

**Component registry** (new, e.g. `frontend/src/lib/panels/registry.ts`):
maps each 1:1 `PanelKey` to its Svelte component. The two special keys
(`indoorAir`, and the `earthquakes`/`lightning` pair) are handled by the plan,
not the registry.

**Pure planner** (new, e.g. `frontend/src/lib/utils/renderPlan.ts`):

```ts
type RenderItem =
  | { kind: 'panel'; key: PanelKey }
  | { kind: 'indoor' }                              // stats row + charts together
  | { kind: 'twocol'; keys: PanelKey[] };           // adjacent eq+lightning

export function buildRenderPlan(
  order: PanelKey[],
  panels: Record<PanelKey, boolean>,
): RenderItem[]
```

Algorithm — walk `order`, considering only **visible** keys:
- `indoorAir` → `{ kind: 'indoor' }`.
- `earthquakes`/`lightning`: if the **next visible** key is the other of the
  pair → emit one `{ kind: 'twocol', keys: [first, second] }` and consume both;
  else emit the single as a normal panel (full-width).
- any other visible key → `{ kind: 'panel', key }`.

`+page.svelte` iterates the plan:
- `panel` → `<svelte:component this={registry[key]} />`
- `indoor` → `<IndoorStatsRow /> <IndoorCharts />`
- `twocol` → `<div class="two-col">` with each key's component via the registry.

Store-init/cleanup (`onMount`/`onDestroy` polling wiring) is unchanged — all
stores keep initialising regardless of order/visibility, exactly as today.

**Default-layout note:** because indoor air is now one block, the indoor charts
move up to sit directly under the indoor stats row (near the top) rather than at
the very bottom. Users can drag the block anywhere afterward.

## Settings reorder interaction (zero-dep)

A small self-contained module drives pointer dragging (e.g. a Svelte action
`frontend/src/lib/actions/reorderable.ts`, or logic colocated in the panels
section component):

- `pointerdown` on a grip → capture pointer, mark the row "lifted".
- `pointermove` → compute target index from pointer Y vs the row midpoints; show
  an insertion gap / lifted-row styling.
- `pointerup` / cancel → commit the new order via `settingsStore.update`, or
  revert on cancel.
- Handle uses `touch-action: none` so touch-drag doesn't scroll the page.
- **↑/↓ buttons and ArrowUp/ArrowDown** on a focused row call the same
  `moveItem(order, from, to)` helper; an `aria-live="polite"` region announces
  "Moved <label> to position N of M".

New pure helper `moveItem(list, from, to)` (unit-tested) does the array move.

The `PanelToggleRow` component is extended (or wrapped by a new
`PanelReorderRow`) to add the grip + ↑/↓ controls while keeping the existing
switch markup/behaviour.

## Testing

- **Unit (vitest):**
  - `mergeOrder`: missing → default; partial → append missing; unknown keys
    dropped; duplicates collapsed; valid permutation preserved.
  - `moveItem`: up, down, no-op, bounds.
  - `buildRenderPlan`: adjacent eq+lightning → one `twocol`; separated →
    two singles; one of the pair hidden → single full-width; `indoorAir` visible
    → `indoor` item; hidden keys omitted; order respected.
- **Component (@testing-library/svelte):** ↑/↓ (and ArrowUp/Down) reorder
  updates `settingsStore.order`; "Reset to defaults" restores default order.
- **Manual (browser preview):** pointer-drag physics (mouse + touch emulation),
  insertion gap, dashboard reflow, both themes. Playwright e2e optional.

## Scope

**In:** reorder all 24 sections; persist to `observatory.settings.v1`; smart
grouping (eq/lightning adjacency, indoor block); mouse + touch + keyboard;
reset restores default order.

**Out (YAGNI):** per-device orders; dragging between show/hide groups;
server-side persistence; animated reflow beyond a simple CSS transition;
reordering the two-col pair's internal left/right beyond their order in the list.

## Files touched (anticipated)

- `frontend/src/lib/utils/settingsSchema.ts` — `order` field, `DEFAULTS`,
  `mergeOrder`, `parseSettings`.
- `frontend/src/lib/utils/renderPlan.ts` *(new)* — `buildRenderPlan`, `moveItem`.
- `frontend/src/lib/panels/registry.ts` *(new)* — `PanelKey → component` map.
- `frontend/src/routes/+page.svelte` — data-driven rendering from the plan.
- `frontend/src/routes/settings/+page.svelte` — reorder list wiring.
- `frontend/src/lib/components/PanelToggleRow.svelte` (or a new
  `PanelReorderRow.svelte`) — grip + ↑/↓ controls.
- `frontend/src/lib/actions/reorderable.ts` *(new, optional)* — pointer-drag.
- Tests under `frontend/src/**/*.test.ts` (+ optional Playwright).
