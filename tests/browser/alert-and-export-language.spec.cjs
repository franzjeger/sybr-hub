// The overview's Excel export asks for the reader's language, and an
// automatic alert's detail is built in the reader's language from the key
// the server sends. The export sent no language and came back in English;
// the alert detail was a Norwegian sentence written when the check ran.
const { test, expect } = require('@playwright/test');
const { inApp, expectSignedIn } = require('./app.cjs');

async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect.poll(async () => (await page.request.get('/api/auth/me')).status()).toBe(200);
  await expectSignedIn(page);
}

test.afterEach(async ({page}) => {
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

for (const lang of ['en', 'no']) {
  test(`the Excel export asks for the reader's language (${lang})`, async ({page}) => {
    await login(page);
    const bodies = [];
    await page.route('**/api/export/excel', route => {
      bodies.push(route.request().postDataJSON());
      route.fulfill({status: 200, contentType: 'text/csv', body: 'Customer;Domain\n'});
    });
    await inApp(page, (app, value) => app.setLanguage(value), lang);
    await inApp(page, app => app.exportDashboardExcel());
    await expect.poll(() => bodies.length).toBe(1);
    expect(bodies[0]).toEqual({lang});
  });
}

test('an alert detail is built in the reader\'s language from its key', async ({page}) => {
  await login(page);
  const alert = {
    detail: 'Sikkerhetspolicyen «Require MFA» er fjernet siden 2026-09-30.',
    detail_key: 'alert_detail_policy_removed',
    detail_params: {policy: 'Require MFA', since: '2026-09-30'},
  };
  await inApp(page, app => app.setLanguage('en'));
  expect(await inApp(page, (app, a) => app.alertDetail(a), alert))
    .toBe('The security policy “Require MFA” has been removed since 2026-09-30.');
  // An entry from before alerts had keys shows the sentence it was stored with.
  expect(await inApp(page, app => app.alertDetail({detail: 'SMBv1 er slått på'})))
    .toBe('SMBv1 er slått på');
});
