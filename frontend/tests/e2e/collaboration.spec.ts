import { test, expect } from '@playwright/test';
import { loginTestUser } from './authHelper';

test.describe('Real-Time Collaboration', () => {
  test('two browser contexts: presence, remote drawing deltas, area saved, and conflict resolution', async ({
    browser,
  }) => {
    // 1. Two separate browser contexts (User A and User B)
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();

    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    try {
      const userA = await loginTestUser(pageA, { displayName: 'Alice' });
      const userB = await loginTestUser(pageB, { displayName: 'Bob' });

      // 2. Presence: User B appears in User A's presence bar (and vice-versa)
      await expect(pageA.getByText('Bob')).toBeVisible({ timeout: 10000 });
      await expect(pageB.getByText('Alice')).toBeVisible({ timeout: 10000 });

      // 3. User A draws a polygon
      await pageA.getByRole('button', { name: /draw polygon/i }).click();
      const mapA = pageA.locator('.leaflet-container');
      await mapA.click({ position: { x: 300, y: 150 } });
      await mapA.click({ position: { x: 400, y: 150 } });

      // User B should see remote drawing deltas / preview in collaborationPane
      await expect(
        pageB.locator('.leaflet-pane.leaflet-collaboration-pane path[stroke="#8b5cf6"]')
      ).toBeAttached({ timeout: 6000 });

      // User A finishes drawing and saves
      await mapA.click({ position: { x: 350, y: 250 } });
      await pageA.keyboard.press('Enter');

      const areaName = `Collab Area ${Date.now()}`;
      await pageA.fill('input[name="areaName"]', areaName);
      await pageA.getByRole('button', { name: /save/i }).click();

      // 4. User B receives AREA_SAVED and sees the area in their list
      await expect(pageA.locator('.area-list')).toContainText(areaName, { timeout: 10000 });
      await expect(pageB.locator('.area-list')).toContainText(areaName, { timeout: 10000 });

      // 5. Concurrent edit of one area -> loser gets ConflictDialog
      // On User A, the newly created area is already selected. If not, select it.
      if (!await pageA.getByRole('button', { name: /edit vertices/i }).isVisible()) {
        await pageA.locator('.area-list').getByText(areaName).first().click();
      }
      // User B selects the created area from their list
      await pageB.locator('.area-list').getByText(areaName).first().click();

      // Both click "Edit Vertices"
      await pageA.getByRole('button', { name: /edit vertices/i }).click();
      await pageB.getByRole('button', { name: /edit vertices/i }).click();

      // Wait for handles to appear
      const handleA = pageA.locator('.snapland-vertex-handle').first();
      await expect(handleA).toBeVisible({ timeout: 5000 });
      const handleB = pageB.locator('.snapland-vertex-handle').first();
      await expect(handleB).toBeVisible({ timeout: 5000 });

      // User A drags a vertex and saves
      const boxA = await handleA.boundingBox();
      if (boxA) {
        await pageA.mouse.move(boxA.x + 5, boxA.y + 5);
        await pageA.mouse.down();
        await pageA.mouse.move(boxA.x + 40, boxA.y + 40);
        await pageA.mouse.up();
      }
      await pageA.getByRole('button', { name: /save vertices/i }).click();

      // User B drags their vertex and attempts to save (or gets proactive conflict)
      const boxB = await handleB.boundingBox();
      if (boxB) {
        await pageB.mouse.move(boxB.x + 5, boxB.y + 5);
        await pageB.mouse.down();
        await pageB.mouse.move(boxB.x + 25, boxB.y + 25);
        await pageB.mouse.up();
      }

      // If User B clicks save, they get 409 Conflict. Or proactive detection fires!
      const saveBtnB = pageB.getByRole('button', { name: /save vertices/i });
      if (await saveBtnB.isVisible()) {
        await saveBtnB.click();
      }

      // Loser gets the ConflictDialog with the current state and options
      await expect(pageB.getByText(/conflict/i)).toBeVisible({ timeout: 10000 });
      await expect(pageB.getByRole('button', { name: /accept remote/i })).toBeVisible();
      await expect(pageB.getByRole('button', { name: /force overwrite/i })).toBeVisible();
      await expect(pageB.getByText(/save as new/i)).toBeVisible();
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
