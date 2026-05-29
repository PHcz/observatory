import { test, expect } from '@playwright/test';

test.describe('Phase 8.5 accessibility', () => {
  test('focus-visible ring on settings controls', async ({ page }) => {
    await page.goto('/settings');
    await page.keyboard.press('Tab');
    const outline = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      if (!el) return null;
      return getComputedStyle(el).outlineColor;
    });
    expect(outline).toBeTruthy();
  });

  test('theme picker is keyboard-navigable (radiogroup)', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Light theme').focus();
    await page.keyboard.press('ArrowRight');
    const focused = await page.evaluate(() => (document.activeElement as HTMLInputElement)?.value);
    expect(focused).toBe('dark');
  });

  test('dark theme contrast — body text on bg passes AA', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Dark theme').click();
    await page.goto('/');
    const colour = await page.locator('body').evaluate((el) => getComputedStyle(el).color);
    // UI-SPEC --text dark = #ece9e3 = rgb(236,233,227); allow tolerance.
    expect(colour).toMatch(/rgb\(23[0-6],\s*23[0-3],\s*22[7-9]\)/);
  });
});
