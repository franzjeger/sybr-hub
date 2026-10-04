// The CSV export asks for the language the report screen is set to, as the
// report itself does. It sent only the customer id, and the server wrote the
// export in Norwegian whatever the screen said.
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
  test(`the CSV export asks for the report language (${lang})`, async ({page}) => {
    await login(page);
    const bodies = [];
    await page.route('**/api/report/csv', route => {
      bodies.push(route.request().postDataJSON());
      route.fulfill({status: 200, contentType: 'text/csv', body: 'Category;Metric;Value;Status\n'});
    });
    // The select sits in the Audit tab's report menu; its value is what counts.
    await page.evaluate(value => { document.getElementById('report-lang').value = value; }, lang);
    await inApp(page, app => app.exportCSV('Browser_Beta'));
    await expect.poll(() => bodies.length).toBe(1);
    expect(bodies[0]).toEqual({customer_id: 'Browser_Beta', lang});
  });
}
