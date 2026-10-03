// Clicking one customer and then another before the first has loaded opens
// the second, and leaves the second as this tab's current customer. The
// first page's read is held back here, so without the guard it would land
// last and paint over the second. There is no customer switch on the server
// any more; what is ordered is the page.
const { test, expect } = require('@playwright/test');
const { inApp } = require('./app.cjs');

async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-switcher');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
}

const ALPHA = 'Browser_Alpha';
const BETA = 'Browser_Beta';

test('the last customer clicked is the one that opens and stays current', async ({page}) => {
  await login(page);

  // The first page's read (Alpha's, asked first) is the slow one.
  let held = false;
  await page.route('**/api/dashboard/overview', async route => {
    if (!held) {
      held = true;
      await new Promise(r => setTimeout(r, 800));
    }
    await route.continue();
  });

  await inApp(page, (app, a, b) => { app.overviewSelectCustomer(a); app.overviewSelectCustomer(b); }, ALPHA, BETA);

  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  await page.waitForTimeout(1200);
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  expect(await inApp(page, app => app.currentCustomerId())).toBe(BETA);
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

test('a tab about one customer follows a customer opened from another page', async ({page}) => {
  await login(page);
  await inApp(page, (app, id) => { app.overviewSelectCustomer(id); }, ALPHA);
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Alpha');
  await inApp(page, (app, id) => { app.overviewSelectCustomer(id); }, BETA);
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  expect(await inApp(page, app => app.currentCustomerId())).toBe(BETA);
  // Policy-oversikt was a page about "the active customer"; it is the open
  // customer's tab now, and reads that customer by name.
  const read = page.waitForRequest(r => r.url().includes('/api/policy-overview/'));
  await inApp(page, app => app.showView('policy-overview'));
  expect((await read).url()).toContain('/api/policy-overview/' + encodeURIComponent(BETA));
});

test('a customer opened before the account has loaded still opens', async ({page}) => {
  await login(page);
  // The state start-up is in before /auth/me answers: no account, no paths
  // known to be open without the write capability. Opening a customer sends
  // nothing that could be refused for that.
  await inApp(page, (app, b) => {
    app.setCurrentUser(null);
    app._writeExempt.length = 0;
    app.overviewSelectCustomer(b);
  }, BETA);
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
});
