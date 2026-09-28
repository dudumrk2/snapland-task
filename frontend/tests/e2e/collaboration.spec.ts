import { test, expect } from '@playwright/test';

test.describe('Collaboration Flow', () => {
  test('A draws, B sees REMOTE_DRAW and AREA_SAVED', async ({ browser }) => {
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    // Setup A and B
    await pageA.goto('/login');
    await pageB.goto('/login');
    // Assume login is bypassed or mocked, or do actual login
    await pageA.fill('input[name="email"]', 'userA@test.com');
    await pageA.fill('input[name="password"]', 'pass');
    await pageA.getByRole('button', { name: /login/i }).click();

    await pageB.fill('input[name="email"]', 'userB@test.com');
    await pageB.fill('input[name="password"]', 'pass');
    await pageB.getByRole('button', { name: /login/i }).click();

    // Check presence
    await expect(pageA.locator('.presence-bar')).toContainText('userB');
    await expect(pageB.locator('.presence-bar')).toContainText('userA');

    // A draws
    await pageA.getByRole('button', { name: /draw polygon/i }).click();
    const mapA = pageA.locator('.leaflet-container');
    await mapA.click({ position: { x: 100, y: 100 } });
    await mapA.click({ position: { x: 200, y: 100 } });

    // B sees remote preview
    const remotePreview = pageB.locator('.remote-preview');
    await expect(remotePreview).toBeVisible();

    // A saves
    await mapA.click({ position: { x: 150, y: 200 } });
    await mapA.dblclick({ position: { x: 100, y: 100 } });
    await pageA.fill('input[name="areaName"]', 'Collab Polygon');
    await pageA.getByRole('button', { name: /save/i }).click();

    // B sees saved area
    const areaListB = pageB.locator('.area-list');
    await expect(areaListB).toContainText('Collab Polygon');
    await expect(remotePreview).not.toBeVisible();
  });

  test('Concurrent edit conflict', async ({ browser }) => {
    // A and B edit the same area
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    await pageA.goto('/');
    await pageB.goto('/');

    // A and B select the same area to edit
    await pageA.locator('.area-item').first().click();
    await pageA.getByRole('button', { name: /edit/i }).click();
    
    await pageB.locator('.area-item').first().click();
    await pageB.getByRole('button', { name: /edit/i }).click();

    // A saves first
    const mapA = pageA.locator('.leaflet-container');
    // Assume vertex drag
    await mapA.mouse.move(100, 100);
    await mapA.mouse.down();
    await mapA.mouse.move(120, 120);
    await mapA.mouse.up();
    await pageA.getByRole('button', { name: /save/i }).click();

    // B tries to save
    const mapB = pageB.locator('.leaflet-container');
    await mapB.mouse.move(150, 150);
    await mapB.mouse.down();
    await mapB.mouse.move(160, 160);
    await mapB.mouse.up();
    await pageB.getByRole('button', { name: /save/i }).click();

    // B gets ConflictDialog
    await expect(pageB.locator('.conflict-dialog')).toBeVisible();
    await expect(pageB.getByRole('button', { name: /accept remote/i })).toBeVisible();
  });
});
