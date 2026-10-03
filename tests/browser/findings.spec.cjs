// The core loop: open a customer, see what is wrong, decide, and turn a
// finding into work in the PSA. The fixture seeds "Browser Beta" with one
// audit run holding three findings; integrations that need a live service
// are answered by routed responses, so what is tested is this page.
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

async function betaId(page) {
  const r = await page.request.get('/api/dashboard/overview');
  const beta = (await r.json()).customers.find(c => c.customer_name === 'Browser Beta');
  return beta.customer_id;
}

// Rewrite the findings answer so an integration reads as set up and/or linked.
async function routeIntegrations(page, integrations) {
  await page.route(url => /\/api\/hub\/[^/]+\/findings$/.test(new URL(url).pathname), async route => {
    const response = await route.fetch();
    const body = await response.json();
    Object.assign(body.integrations, integrations);
    await route.fulfill({response, json: body});
  });
}

test('the customer page puts the findings first, worst first, for the customer it names', async ({page}) => {
  await login(page);
  const id = await betaId(page);
  await page.goto('/#/customer/' + encodeURIComponent(id));
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  await expect(page.locator('#active-customer-name')).toHaveText('Browser Beta');
  const rows = page.locator('#cust-findings .finding');
  await expect(rows).toHaveCount(3);
  await expect(rows.locator('.sev-chip')).toHaveText(['Kritisk', 'Høy', 'Lav']);
  // Nothing to push to yet: one notice, no dead buttons on the rows.
  await expect(page.locator('#cust-findings .findings-notice')).toHaveCount(1);
  await expect(page.locator('#cust-findings [data-action="push"]')).toHaveCount(0);
});

test('a decision on a finding survives a reload', async ({page}) => {
  await login(page);
  const id = await betaId(page);
  await page.goto('/#/customer/' + encodeURIComponent(id));
  const first = page.locator('#cust-findings .finding').first();
  await first.locator('.finding-status').selectOption('in_progress');
  await expect(page.locator('#cust-findings .findings-summary')).toContainText('1 pågår');
  await page.reload();
  await expect(page.locator('#cust-findings .finding').first().locator('.finding-status')).toHaveValue('in_progress');
  // Leave the shared fixture as it was for the other tests.
  await page.locator('#cust-findings .finding').first().locator('.finding-status').selectOption('open');
  await expect(page.locator('#cust-findings .findings-summary')).toContainText('0 pågår');
});

test('a linked customer turns a finding into a ticket and shows its number', async ({page}) => {
  await login(page);
  const id = await betaId(page);
  await routeIntegrations(page, {autotask: {configured: true, linked: true}});
  let sent = null;
  await page.route(url => new URL(url).pathname === '/api/hub/' + encodeURIComponent(id) + '/tickets', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    sent = route.request().postDataJSON();
    await route.fulfill({json: {ok: true, created: true, ticket: {external_id: '4711', external_url: 'https://example.invalid/t/4711'}}});
  });
  await page.goto('/#/customer/' + encodeURIComponent(id));
  const crit = page.locator('#cust-findings .finding').first();
  await crit.getByRole('button', {name: 'Opprett sak'}).click();
  await expect(crit.locator('.tk-title')).toHaveValue('Global administrator uten MFA');
  await expect(crit.locator('.tk-priority')).toHaveValue('1');
  await crit.locator('[data-action="submit-push"]').click();
  await expect(crit.locator('.push-done')).toContainText('4711');
  await expect(crit.locator('.push-done')).toHaveAttribute('rel', /noopener/);
  expect(sent).toMatchObject({rec_id: 'fx-crit', title: 'Global administrator uten MFA', priority: 1});
});

test('a configured but unlinked PSA offers one way to link, and the picker suggests by name', async ({page}) => {
  await login(page);
  const id = await betaId(page);
  await routeIntegrations(page, {autotask: {configured: true, linked: false}});
  await page.route(url => new URL(url).pathname === '/api/autotask/accounts', route => route.fulfill({json: {accounts: [
    {id: 11, name: 'Annen Kunde AS'},
    {id: 22, name: 'Browser Beta'},
  ]}}));
  await page.goto('/#/customer/' + encodeURIComponent(id));
  await page.locator('#cust-findings [data-action="link"][data-system="autotask"]').click();
  const picker = page.locator('.link-picker');
  await expect(picker).toBeVisible();
  await expect(picker.locator('.link-result').first()).toContainText('Browser Beta');
  // Linking re-reads the findings. Wait for that answer, or under a loaded
  // parallel run the request was still in the route handler when the test
  // ended, and the test failed after every assertion had passed.
  const reread = page.waitForResponse(r => /\/api\/hub\/[^/]+\/findings$/.test(new URL(r.url()).pathname));
  await picker.locator('.link-result').first().click();
  await expect(picker).toHaveCount(0);
  await reread;
  const record = await (await page.request.get('/api/hub/' + encodeURIComponent(id))).json();
  expect(record.autotask.status).not.toBe('not_linked');
  // Undo through the same picker, so the shared fixture is unchanged.
  await page.request.post('/api/hub/' + encodeURIComponent(id) + '/link', {data: {autotask_account_id: null}});
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

test('the picker closes on Escape without saving', async ({page}) => {
  await login(page);
  const id = await betaId(page);
  await routeIntegrations(page, {myitprocess: {configured: true, linked: false}});
  await page.route(url => new URL(url).pathname === '/api/myitprocess/accounts', route => route.fulfill({json: {accounts: [{id: 'm-1', name: 'Browser Beta'}]}}));
  await page.goto('/#/customer/' + encodeURIComponent(id));
  await page.locator('#cust-findings [data-action="link"][data-system="myitprocess"]').click();
  await expect(page.locator('.link-picker')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.link-picker')).toHaveCount(0);
});

test('a customer without M365 access says so instead of offering an audit that would fail', async ({page}) => {
  await login(page);
  const r = await page.request.get('/api/dashboard/overview');
  const alpha = (await r.json()).customers.find(c => c.customer_name === 'Browser Alpha');
  await page.goto('/#/customer/' + encodeURIComponent(alpha.customer_id));
  await expect(page.locator('#cust-run-audit')).toBeDisabled();
  await expect(page.locator('.cust-access-notice')).toBeVisible();
  await expect(page.locator('#cust-findings .findings-empty-title')).toHaveText('Ikke auditert ennå');
});
