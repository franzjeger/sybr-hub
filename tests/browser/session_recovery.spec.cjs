const {test, expect} = require('@playwright/test');

async function prepare(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'en');
  });
}

async function login(page) {
  await prepare(page);
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expect.poll(() => page.evaluate(() => !!_currentUser && !!_i18n.en)).toBe(true);
}

async function dropAccessCookie(page) {
  const cookies = await page.context().cookies();
  await page.context().clearCookies();
  await page.context().addCookies(cookies.filter(c => c.name !== 'access_token'));
}

async function refreshCookie(page) {
  return (await page.context().cookies()).find(c => c.name === 'refresh_token').value;
}

test('a signed-out API call shows the login form, not a lost-connection alarm', async ({page}) => {
  await prepare(page);
  await page.goto('/');
  await expect(page.locator('#login-password')).toBeVisible();
  await expect.poll(() => page.evaluate(() => !!_i18n.en)).toBe(true);
  // Goes through session recovery against the real server: no access and no
  // refresh cookie, which is every first visit.
  expect(await page.evaluate(() => apiFetch('/api/status'))).toBeNull();
  await expect(page.locator('#login-password')).toBeVisible();
  await expect(page.getByText('Lost connection to server')).toHaveCount(0);
});

test('a refresh the server refuses with 400 signs out instead of alarming', async ({page}) => {
  await login(page);
  await page.route('**/api/auth/me', route => route.fulfill({status: 401, json: {error: 'expired'}}));
  await page.route('**/api/auth/refresh', route => route.fulfill({status: 400, json: {error: 'missing'}}));
  await page.evaluate(() => apiFetch('/api/auth/me'));
  await expect(page.locator('#login-password')).toBeVisible();
  await expect(page.getByText('Lost connection to server')).toHaveCount(0);
});

test('each recovery rotates the refresh cookie and the next one uses it', async ({page}) => {
  await login(page);
  for (let round = 0; round < 2; round++) {
    const before = await refreshCookie(page);
    await dropAccessCookie(page);
    const me = await page.evaluate(() => apiFetch('/api/auth/me'));
    expect(me && me.user).toBeTruthy();
    expect(await refreshCookie(page)).not.toBe(before);
  }
  await expect(page.locator('#login-password')).not.toBeVisible();
});
