import { test, expect } from '@playwright/test';

test.describe('UI-17 theme switching', () => {
  test('selecting Dark applies data-theme=dark to <html>', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Dark theme').click();
    const theme = await page.locator('html').getAttribute('data-theme');
    expect(theme).toBe('dark');
  });

  test('chart strokes use dark token after theme swap', async ({ page }) => {
    await page.goto('/');
    await page.goto('/settings');
    await page.getByLabel('Dark theme').click();
    await page.goto('/');
    const path = page.locator('section').filter({ hasText: 'Muon flux' }).locator('path').first();
    const stroke = await path.evaluate((el) => getComputedStyle(el).stroke);
    // Dark --chart-data #ece9e3 = rgb(236,233,227); allow tolerance.
    expect(stroke).toMatch(/rgb\((23[0-9]|24[0-9]),\s*(23[0-9]|24[0-9]),\s*(22[0-9]|23[0-9])\)/);
  });
});
