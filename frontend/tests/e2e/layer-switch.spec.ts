import { test, expect } from '@playwright/test';
import { loginTestUser } from './authHelper';

test.describe('Layer Switch Flow', () => {
  test('switch OSM <-> satellite', async ({ page }) => {
    await loginTestUser(page);

    // Draw and save a polygon
    await page.getByRole('button', { name: /draw polygon/i }).click();
    const map = page.locator('.leaflet-container');
    await map.click({ position: { x: 300, y: 120 } });
    await map.click({ position: { x: 400, y: 120 } });
    await map.click({ position: { x: 350, y: 220 } });
    await page.keyboard.press('Enter');

    const areaName = `Switch Area ${Date.now()}`;
    await page.fill('input[name="areaName"]', areaName);
    await page.getByRole('button', { name: /save/i }).click();

    // Verify polygon is visible in area list
    await expect(page.locator('.area-list')).toContainText(areaName, { timeout: 10000 });

    const polygon = page.locator('path.snapland-area-polygon').last();
    await expect(polygon).toBeVisible();

    // Store polygon screen position (SVG d attribute), LatLngs, and map state before switch
    const beforeD = await polygon.getAttribute('d');
    expect(beforeD).toBeTruthy();

    const latLngsBefore = await page.evaluate(() => {
      const m = (window as unknown as { snaplandMap?: { eachLayer: (cb: (l: { getLatLngs?: () => unknown }) => void) => void } }).snaplandMap;
      let lls: unknown = null;
      m?.eachLayer((l) => {
        if (l.getLatLngs) lls = l.getLatLngs();
      });
      return lls;
    });

    const mapStateBefore = await page.evaluate(() => {
      const m = (window as unknown as {
        snaplandMap?: {
          getCenter: () => { lat: number; lng: number };
          getZoom: () => number;
        };
      }).snaplandMap;
      return m ? { center: m.getCenter(), zoom: m.getZoom() } : null;
    });

    // Switch to satellite
    await page.getByRole('button', { name: /satellite/i }).click();

    // Verify polygon screen position (d attribute) unchanged
    const afterD = await polygon.getAttribute('d');
    expect(afterD).toBe(beforeD);

    // Verify polygon LatLngs unchanged
    const latLngsAfter = await page.evaluate(() => {
      const m = (window as unknown as { snaplandMap?: { eachLayer: (cb: (l: { getLatLngs?: () => unknown }) => void) => void } }).snaplandMap;
      let lls: unknown = null;
      m?.eachLayer((l) => {
        if (l.getLatLngs) lls = l.getLatLngs();
      });
      return lls;
    });
    expect(latLngsAfter).toEqual(latLngsBefore);

    // Verify map center/zoom unchanged
    const mapStateAfter = await page.evaluate(() => {
      const m = (window as unknown as {
        snaplandMap?: {
          getCenter: () => { lat: number; lng: number };
          getZoom: () => number;
        };
      }).snaplandMap;
      return m ? { center: m.getCenter(), zoom: m.getZoom() } : null;
    });
    if (mapStateBefore && mapStateAfter) {
      expect(mapStateAfter.zoom).toEqual(mapStateBefore.zoom);
      expect(mapStateAfter.center.lat).toBeCloseTo(mapStateBefore.center.lat, 4);
      expect(mapStateAfter.center.lng).toBeCloseTo(mapStateBefore.center.lng, 4);
    }

    // Switch back to OSM
    await page.getByRole('button', { name: /osm/i }).click();
    const backD = await polygon.getAttribute('d');
    expect(backD).toBe(beforeD);

    // Start drawing (in progress)
    await page.getByRole('button', { name: /draw polygon/i }).click();
    await map.click({ position: { x: 500, y: 300 } });

    // Switch back and forth while drawing is in progress
    await page.getByRole('button', { name: /satellite/i }).click();

    // Ensure drawing in progress survives the switch (add second vertex, cancel is visible)
    await map.click({ position: { x: 550, y: 350 } });
    await expect(page.getByRole('button', { name: /cancel/i }).first()).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('fallback on govmap failure', async ({ page }) => {
    // Route tile requests to 403
    await page.route('**/*govmap.gov.il*/**', (route) => route.abort('accessdenied'));

    await loginTestUser(page);
    await page.getByRole('button', { name: /satellite/i }).click();

    // Expect Esri fallback
    const toast = page.locator('.toast');
    await expect(toast).toContainText(/fallback/i, { timeout: 10000 });

    // Check if Esri tiles are requested
    const esriLayer = page.locator('img[src*="arcgisonline.com"]').first();
    await expect(esriLayer).toBeVisible({ timeout: 10000 });
  });
});
