// Automatisk audit of one customer names the customer. The mode used to audit
// the setup staging slot (the customer set up last) and its hint called that
// "the active customer". The settings now pick a customer from the list and
// store its id; settings from before that, which say "one customer" without
// saying which, show a placeholder and say the audit does not run.
const { test, expect } = require('@playwright/test');
const { expectSignedIn } = require('./app.cjs');

async function login(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

async function openAlertsPane(page) {
  await page.evaluate(() => { location.hash = '#/admin/alerts'; });
  await expect(page.locator('#admin-pane-alerts')).toBeVisible();
}

const SAVE = '#admin-pane-alerts [data-click-handler="saveSettings"]';

test('the automatic audit names its one customer, and settings that name none say so', async ({page}) => {
  await login(page);
  try {
    await openAlertsPane(page);
    const picker = page.locator('#input-scheduler-customer');
    const warning = page.locator('#scheduler-customer-warning');

    // Every customer, then the customers by name. Nothing about an active one.
    // (Other specs add customers to the shared fixture, so not the whole list.)
    await expect(picker.locator('option').first()).toHaveText('Alle kunder som er satt opp for audit');
    await expect(picker.locator('option[value="Browser_Alpha"]')).toHaveText('Browser Alpha');
    await expect(picker.locator('option[value="Browser_Beta"]')).toHaveText('Browser Beta');
    await expect(picker).toHaveValue('');
    await expect(warning).toBeHidden();
    await expect(page.locator('#admin-pane-alerts')).not.toContainText('aktiv kunde');

    // One customer, chosen and saved by id.
    await picker.selectOption('Browser_Beta');
    const posted = page.waitForRequest(r => r.method() === 'POST' && new URL(r.url()).pathname === '/api/scheduler');
    await page.locator(SAVE).click();
    const body = (await posted).postDataJSON();
    expect(body.audit_all_customers).toBe(false);
    expect(body.customer_id).toBe('Browser_Beta');
    await expect.poll(async () => (await (await page.request.get('/api/scheduler')).json()).customer_id).toBe('Browser_Beta');

    // Settings from before the id: one customer, none named. The page says
    // the audit does not run, and a save with the placeholder still chosen
    // leaves the stored choice alone instead of guessing one.
    await page.route('**/api/scheduler', route => route.request().method() === 'GET'
      ? route.fulfill({json: {enabled: true, interval_hours: 168, audit_all_customers: false, customer_id: null, webhook_url: '', alert_on: {}}})
      : route.continue());
    await page.reload();
    await expectSignedIn(page);
    await openAlertsPane(page);
    await expect(picker).toHaveValue('?');
    await expect(picker.locator('option:checked')).toHaveText('Én kunde, ikke valgt');
    await expect(warning).toBeVisible();
    await expect(warning).toHaveText(/kjører derfor ikke/);
    const untouched = page.waitForRequest(r => r.method() === 'POST' && new URL(r.url()).pathname === '/api/scheduler');
    await page.locator(SAVE).click();
    const kept = (await untouched).postDataJSON();
    expect(kept).not.toHaveProperty('audit_all_customers');
    expect(kept).not.toHaveProperty('customer_id');
  } finally {
    // Back to the fixture's every-customer mode for the specs after this one.
    await page.unrouteAll({behavior: 'ignoreErrors'});
    await page.request.post('/api/scheduler', {data: {audit_all_customers: true}});
  }
});
