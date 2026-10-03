// A form opened while its view's list is still loading stays open when the
// list arrives. The list request is held back here, the way a slow server
// (or a CI runner) holds it, so without the claim the late answer would
// redraw the box and the form would vanish.
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  // Let start-up land first. It applies the route from the address bar (here
  // the dashboard), which on a slow runner came after the test had opened its
  // form: a real navigation, not the race this file is about.
  await expect(page.locator('body')).toHaveAttribute('data-view', 'overview');
}

async function holdBack(page, pattern) {
  let release;
  const released = new Promise(r => { release = r; });
  await page.route(pattern, async route => {
    await released;
    await route.continue();
  });
  return release;
}

test('the new VPN profile form survives a list that loads late', async ({page}) => {
  await login(page);
  const release = await holdBack(page, '**/api/vpn/profiles');
  await page.evaluate(() => showView('vpn'));
  await page.locator('#view-vpn [data-click-handler="vpnShowCreate"]').click();
  await expect(page.locator('#vpn-create-protocol')).toBeVisible();
  release();
  await page.waitForResponse('**/api/vpn/status');
  await page.waitForTimeout(300);
  await expect(page.locator('#vpn-create-protocol')).toBeVisible();
});

test('the SSH key generator survives a key list that loads late', async ({page}) => {
  await login(page);
  const release = await holdBack(page, '**/api/ssh/keys');
  await page.evaluate(() => showView('ssh'));
  await page.evaluate(() => sshGenKey());
  await expect(page.locator('#ssh-content input, #ssh-content select').first()).toBeVisible();
  const form = await page.locator('#ssh-content').innerHTML();
  release();
  await page.waitForResponse('**/api/ssh/keys');
  await page.waitForTimeout(300);
  expect(await page.locator('#ssh-content').innerHTML()).toBe(form);
});
