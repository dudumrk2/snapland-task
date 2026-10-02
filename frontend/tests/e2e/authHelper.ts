import { Page } from '@playwright/test';

export async function loginTestUser(
  page: Page,
  options?: {
    email?: string;
    password?: string;
    displayName?: string;
  }
): Promise<{ email: string; displayName: string }> {
  const email =
    options?.email ||
    `user-${Date.now()}-${Math.random().toString(36).substring(2, 7)}@example.com`;
  const password = options?.password || 'password123';
  const displayName = options?.displayName || 'Test User';

  await page.goto('/login');

  // Register
  const registerButton = page.getByRole('button', { name: /register/i });
  await registerButton.click();

  await page.fill('input[name="displayName"]', displayName);
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', password);
  await page.getByRole('button', { name: /submit/i }).click();

  // Fresh navigation to login form
  await page.goto('/login');
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', password);
  await page.getByRole('button', { name: /login/i }).click();

  // Wait for map to load
  await page.waitForSelector('.leaflet-container', { timeout: 10000 });

  return { email, displayName };
}
