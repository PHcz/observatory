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
