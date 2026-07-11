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
