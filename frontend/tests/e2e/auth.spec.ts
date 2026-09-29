import { test, expect } from '@playwright/test';

test.describe('Auth Flow', () => {
  test('register -> login -> map -> reload -> logout', async ({ page }) => {
    await page.goto('/login');
    
    // Switch to register
    await page.getByRole('button', { name: /register/i }).click();
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'password123');
    await page.fill('input[name="displayName"]', 'Test User');
    await page.getByRole('button', { name: /submit/i }).click();

    // After register, it should probably route to map or login
    await page.goto('/login');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'password123');
    await page.getByRole('button', { name: /login/i }).click();

    // Map page should be visible
    await expect(page.locator('.leaflet-container')).toBeVisible();

    // Reload page
    await page.reload();

    // Should still be on map page (session restored)
    await expect(page.locator('.leaflet-container')).toBeVisible();

    // Logout
    await page.getByRole('button', { name: /logout/i }).click();

    // Should redirect back to login
    await expect(page.getByRole('button', { name: /login/i })).toBeVisible();
  });
});
