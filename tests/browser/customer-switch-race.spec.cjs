// Clicking one customer and then another before the first has loaded opens
// the second, and leaves the second active on the server. The first switch
// is held back here, so without ordering it would land last and win. It signs
// in as its own user, because the active customer is per user and other specs
// running alongside read browser-admin's.
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-switcher');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
}

test('the last customer clicked is the one that opens and stays active', async ({page}) => {
  await login(page);
  const customers = await (await page.request.get('/api/customers')).json();
  const list = customers.customers || customers;
  const alpha = list.find(c => (c.CustomerName || c.customer_name) === 'Browser Alpha');
  const beta = list.find(c => (c.CustomerName || c.customer_name) === 'Browser Beta');
  const idOf = c => c._id || c.customer_id;

  let held = false;
  await page.route('**/api/customers/switch', async route => {
    const body = route.request().postDataJSON();
    if (!held && body.customer_id === idOf(alpha)) {
      held = true;
      await new Promise(r => setTimeout(r, 800));
    }
    await route.continue();
  });

  await page.evaluate(([a, b]) => { overviewSelectCustomer(a); overviewSelectCustomer(b); },
    [idOf(alpha), idOf(beta)]);

  await expect(page.locator('#customer-detail-content')).toContainText('Browser Beta');
  await page.waitForTimeout(1200);
  await expect(page.locator('#customer-detail-content')).toContainText('Browser Beta');
  const overview = await (await page.request.get('/api/dashboard/overview')).json();
  expect(overview.active_id).toBe(idOf(beta));
});

test('a view about the active customer follows a switch made from another page', async ({page}) => {
  await login(page);
  const customers = await (await page.request.get('/api/customers')).json();
  const list = customers.customers || customers;
  const idOf = name => { const c = list.find(x => (x.CustomerName || x.customer_name) === name); return c._id || c.customer_id; };
  // Kunder caches the active customer; opening another one elsewhere must
  // move that cache, or Policy-oversikt reads the customer before.
  await page.evaluate(id => switchActiveCustomer(id), idOf('Browser Alpha'));
  await page.evaluate(() => loadCustomers());
  await expect.poll(() => page.evaluate(() => _customersActiveId)).toBe(idOf('Browser Alpha'));
  await page.evaluate(id => overviewSelectCustomer(id), idOf('Browser Beta'));
  await expect(page.locator('#customer-detail-content')).toContainText('Browser Beta');
  expect(await page.evaluate(() => _customersActiveId)).toBe(idOf('Browser Beta'));
  const read = page.waitForRequest(r => r.url().includes('/api/policy-overview/'));
  await page.evaluate(() => showView('policy-overview'));
  expect((await read).url()).toContain('/api/policy-overview/' + encodeURIComponent(idOf('Browser Beta')));
});

test('a customer switch made before the account has loaded is sent, not refused', async ({page}) => {
  await login(page);
  const customers = await (await page.request.get('/api/customers')).json();
  const list = customers.customers || customers;
  const beta = list.find(c => (c.CustomerName || c.customer_name) === 'Browser Beta');
  const id = beta._id || beta.customer_id;
  // The state start-up is in before /auth/me answers: no account, no paths
  // known to be open without the write capability.
  await page.evaluate(b => { _currentUser = null; _writeExempt = []; overviewSelectCustomer(b); }, id);
  await expect(page.locator('#customer-detail-content')).toContainText('Browser Beta');
});
