import { test, expect } from '@playwright/test';

test.describe('UI-18 local-quake highlighting', () => {
  test('BGS row has is-local class with sage left border', async ({ page }) => {
    await page.goto('/');
    const localRow = page.locator('.quake-row.is-local').first();
    await expect(localRow).toBeVisible({ timeout: 10000 });
    const borderLeft = await localRow.evaluate((el) => getComputedStyle(el).borderLeftWidth);
    expect(borderLeft).toBe('4px');
  });

  test('local row has aria-label prefix "Local event:"', async ({ page }) => {
    await page.goto('/');
    const localRow = page.locator('.quake-row.is-local').first();
    const ariaLabel = await localRow.getAttribute('aria-label');
    expect(ariaLabel).toMatch(/^Local event:/);
  });
});
