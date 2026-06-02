import { test, expect } from '@playwright/test';

test.describe('UI-16/UI-19 new chart panels honour visibility toggle', () => {
  test('PressureChart visible by default', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('pressure-chart')).toBeVisible();
  });

  test('PressureChart hidden after toggle off', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Show Pressure chart panel').click();
    await page.goto('/');
    await expect(page.getByTestId('pressure-chart')).toHaveCount(0);
  });

  test('HumidityChart + LightChart visible by default', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('humidity-chart')).toBeVisible();
    await expect(page.getByTestId('light-chart')).toBeVisible();
  });
});
