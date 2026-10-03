// On a phone the page fits the screen: no sideways scroll, and every header
// control, the account button included, is on screen.
const { test, expect } = require('@playwright/test');

test.use({ viewport: { width: 375, height: 812 } });

async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
}

async function overflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

test('the dashboard fits a 375 px screen', async ({page}) => {
  await login(page);
  await expect(page.locator('#avatar-btn')).toBeVisible();
  await expect(page.locator('.bnav-item').first()).toBeVisible();
  expect(await overflow(page)).toBe(0);
  const right = await page.locator('#avatar-btn').evaluate(el => el.getBoundingClientRect().right);
  expect(right).toBeLessThanOrEqual(375);
  const lastTab = await page.locator('.bnav-item').last().evaluate(el => el.getBoundingClientRect().right);
  expect(lastTab).toBeLessThanOrEqual(375);
});

test('a search field reads in the body face, not the code face', async ({page}) => {
  await login(page);
  const search = page.locator('#overview-search');
  await expect(search).toBeVisible();
  const font = await search.evaluate(el => getComputedStyle(el).fontFamily);
  expect(font).not.toContain('monospace');
});

test('Mer opens as a sheet that fits the screen, down to Logg ut', async ({page}) => {
  await login(page);
  await page.locator('.bnav-item[data-bnav="more"]').click();
  const sheet = page.locator('#more-sheet');
  await expect(sheet).toBeVisible();
  const box = await sheet.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  const logout = sheet.locator('[data-click-handler="moreSheetLogout"]');
  await logout.scrollIntoViewIfNeeded();
  await expect(logout).toBeInViewport();
  expect(await overflow(page)).toBe(0);
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
});
