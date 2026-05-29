import { test, expect } from '@playwright/test';

test.describe('UI-16 /settings route', () => {
  test('navigate to /settings shows page title', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });

  test('toggling a panel switch hides it on dashboard', async ({ page }) => {
    await page.goto('/settings');
    const lightningSwitch = page.getByLabel('Show Lightning panel');
    await lightningSwitch.click();
    await page.goto('/');
    await expect(page.locator('[data-testid="lightning-panel"]')).toHaveCount(0);
  });

  test('settings survive a hard reload of /settings', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Show Aurora panel').click();
    await page.reload();
    await expect(page.getByLabel('Show Aurora panel')).not.toBeChecked();
  });

  test('reset button restores defaults', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Show Header panel').click();
    await page.getByRole('link', { name: /reset.+defaults/i }).click();
    await expect(page.getByLabel('Show Header panel')).toBeChecked();
  });
});
