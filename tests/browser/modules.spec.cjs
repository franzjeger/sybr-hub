// A module switched off in Settings is gone from the interface after the
// reload the switch triggers, and its routes answer 404.
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect.poll(async () => (await page.request.get('/api/auth/me')).status()).toBe(200);
  await expect(page.locator('#login-password')).not.toBeVisible();
}

test('switching the AI module off in Settings removes it everywhere', async ({page}) => {
  await login(page);
  await expect(page.locator('#nav-ai')).toBeVisible();
  try {
    await page.evaluate(() => openSettings());
    await page.locator('.settings-tab-btn', {hasText: 'Moduler'}).click();
    const toggle = page.locator('.module-toggle[data-module-key="ai"]');
    await expect(toggle).toBeChecked();
    await toggle.uncheck();
    await page.waitForEvent('load');
    await expect(page.locator('#nav-ai')).toBeHidden();
    expect((await page.request.get('/api/claude/status')).status()).toBe(404);
    const me = await (await page.request.get('/api/auth/me')).json();
    expect(me.modules).not.toContain('ai');
  } finally {
    await page.request.put('/api/settings/modules', {data: {ai: true}});
  }
});
