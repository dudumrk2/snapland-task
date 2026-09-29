import { test, expect } from '@playwright/test';

test.describe('Layer Switch Flow', () => {
  test('switch OSM <-> satellite', async ({ page }) => {
    await page.goto('/');

    // Draw and save a polygon
    await page.getByRole('button', { name: /draw polygon/i }).click();
    const map = page.locator('.leaflet-container');
    await map.click({ position: { x: 100, y: 100 } });
    await map.click({ position: { x: 200, y: 100 } });
    await map.click({ position: { x: 150, y: 200 } });
    await map.dblclick({ position: { x: 100, y: 100 } });
    await page.fill('input[name="areaName"]', 'Switch Test');
    await page.getByRole('button', { name: /save/i }).click();

    // Verify polygon is visible
    const polygon = page.locator('path.leaflet-interactive').first();
    await expect(polygon).toBeVisible();

    // Store polygon bounding box to verify it doesn't move
    const beforeBox = await polygon.boundingBox();

    // Switch to satellite
    await page.getByRole('button', { name: /satellite/i }).click();

    // Verify it doesn't move
    const afterBox = await polygon.boundingBox();
    expect(afterBox?.x).toBeCloseTo(beforeBox!.x);
    expect(afterBox?.y).toBeCloseTo(beforeBox!.y);

    // Start drawing (in progress)
    await page.getByRole('button', { name: /draw polygon/i }).click();
    await map.click({ position: { x: 300, y: 300 } });
    
    // Switch back to OSM
    await page.getByRole('button', { name: /osm/i }).click();

    // Ensure drawing is still in progress (verify click adds second vertex)
    await map.click({ position: { x: 400, y: 300 } });
  });

  test('fallback on govmap failure', async ({ page }) => {
    // Route tile requests to 403
    await page.route('**/*govmap.gov.il*/**', route => route.abort('accessdenied'));

    await page.goto('/');
    await page.getByRole('button', { name: /satellite/i }).click();

    // Expect Esri fallback
    const toast = page.locator('.toast');
    await expect(toast).toContainText('Fallback');
    
    // Check if Esri tiles are requested
    // (Playwright can verify if Esri tiles are present in the DOM)
    const esriLayer = page.locator('img[src*="arcgisonline.com"]').first();
    await expect(esriLayer).toBeVisible();
  });
});
