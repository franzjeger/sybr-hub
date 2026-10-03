// Start-up asks the server for each answer once. The bootstrap ran twice
// (checkAuth after the strings had loaded, and again at the end of
// app-chrome.js), so every page load sent /auth/me, /settings, the bell's
// /activity-log and the VPN badge's /vpn/status twice, and opened the
// address's customer page twice.
const { test, expect } = require('@playwright/test');

const PASSWORD = 'Browser-test123!';

async function login(page) {
  await page.goto('/');
  await page.locator('#login-username').fill('browser-tabs');
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expect.poll(() => page.evaluate(() => !!_currentUser && !!_i18n.no)).toBe(true);
}

test('a page load asks the server for each start-up answer once', async ({browser}) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await login(await context.newPage());
  // A fresh tab of the signed-in session: the whole start-up, from nothing.
  const page = await context.newPage();
  const calls = [];
  page.on('request', req => {
    const url = new URL(req.url());
    if (url.pathname.startsWith('/api/')) calls.push(url.pathname + url.search);
  });
  await page.goto('/#/customer/Browser_Beta');
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  const startUp = ['/api/auth/me', '/api/settings', '/api/activity-log?limit=5', '/api/vpn/status'];
  const count = path => calls.filter(c => c === path).length;
  // Each asked at least once; then time for a second round to show up, which
  // is what happened when start-up ran twice.
  await expect.poll(() => startUp.filter(path => count(path) === 0)).toEqual([]);
  await page.waitForTimeout(1500);
  for (const path of startUp) expect(count(path), path).toBe(1);
  await context.close();
});
