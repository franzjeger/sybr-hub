const {test, expect} = require('@playwright/test');
const {expectSignedIn} = require('./app.cjs');

for (const language of ['no', 'en']) {
  test(`risk coverage shows the measured gaps in ${language} on desktop and mobile`, async ({page}) => {
    await page.addInitScript(lang => {
      localStorage.setItem('onboarding_done', '1');
      localStorage.setItem('ui_lang', lang);
    }, language);
    let coverage = {state:'partial',issues:[{no:'MFA er bare målt for 10 av 100 brukere.',en:'MFA was measured for only 10 of 100 users.'}]};
    await page.route('**/api/dashboard/overview', async route => {
      const response = await route.fetch();
      const body = await response.json();
      body.customers.find(c => c.customer_id === 'Browser_Beta').metrics.risk_coverage = coverage;
      await route.fulfill({response,json:body});
    });
    await page.goto('/');
    await page.locator('#login-username').fill('browser-admin');
    await page.locator('#login-password').fill('Browser-test123!');
    await page.locator('#login-password').press('Enter');
    await expectSignedIn(page);
    await page.goto('/#/customer/Browser_Beta/funn');
    const card = page.locator('#cust-risk-coverage');
    await expect(card).toContainText(language === 'no' ? 'ufullstendige data' : 'incomplete data');
    await expect(card).toContainText(coverage.issues[0][language]);
    await expect(page.locator('#cust-findings .findings-summary')).toBeVisible();
    await page.screenshot({path:`/tmp/sybrhub-risk-${language}-desktop.png`,fullPage:true,animations:'disabled'});
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:`/tmp/sybrhub-risk-${language}-mobile.png`,fullPage:true,animations:'disabled'});
    coverage = null;
    await page.reload();
    await expect(card).toContainText(language === 'no' ? 'ikke lagret datadekning' : 'did not store evidence coverage');
  });
}

test.afterEach(async ({page}) => {
  await page.unrouteAll({behavior:'wait'});
});
