import { describe, it, expect } from 'vitest';
import { PANEL_COMPONENTS } from '#lib/panels/registry.js';
import { ALL_PANELS } from '#lib/utils/settingsSchema.js';

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
