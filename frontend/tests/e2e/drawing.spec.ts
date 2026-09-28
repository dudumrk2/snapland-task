import { test, expect } from '@playwright/test';

test.describe('Drawing Flow', () => {
  test('draw a polygon and save', async ({ page }) => {
    await page.goto('/');

    // Start drawing
    await page.getByRole('button', { name: /draw polygon/i }).click();

    // Click on map to add vertices
    const map = page.locator('.leaflet-container');
    await map.click({ position: { x: 100, y: 100 } });
    await map.click({ position: { x: 200, y: 100 } });
    await map.click({ position: { x: 150, y: 200 } });

    // Double click to finish
    await map.dblclick({ position: { x: 100, y: 100 } });

    // Save dialog should appear
    await page.fill('input[name="areaName"]', 'Test Polygon');
    await page.getByRole('button', { name: /save/i }).click();

    // Polygon should appear in the list with server area
    const areaList = page.locator('.area-list');
    await expect(areaList).toContainText('Test Polygon');
    // Ensure it has server km2 (not the approx ≈)
    await expect(areaList.locator('text=km²')).toBeVisible();
    await expect(areaList.locator('text=≈')).not.toBeVisible();
  });
});
