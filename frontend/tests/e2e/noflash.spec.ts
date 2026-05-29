import { test, expect } from '@playwright/test';

test.describe('UI-17 no-flash hydration', () => {
  test('cold-load with dark setting paints dark before SvelteKit hydrates', async ({ page, context }) => {
    await context.addInitScript(() => {
      localStorage.setItem('observatory.settings.v1', JSON.stringify({ theme: 'dark', panels: {} }));
    });
    await page.goto('/');
    const theme = await page.locator('html').getAttribute('data-theme');
    expect(theme).toBe('dark');
  });
});
