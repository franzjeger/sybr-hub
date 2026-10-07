const {test, expect} = require('@playwright/test');
const {inApp, expectSignedIn} = require('./app.cjs');

for (const language of ['en', 'no']) {
  test(`renewal retains credentials and sends the selected customer (${language})`, async ({page}) => {
    await page.addInitScript(lang => {
      localStorage.setItem('onboarding_done', '1');
      localStorage.setItem('ui_lang', lang);
    }, language);
    let wipes = 0;
    let callbackBody;
    await page.route('**/api/customer/renew', route => {
      wipes++;
      return route.fulfill({json:{ok:true}});
    });
    await page.route('**/api/setup/pkce/start', route => route.fulfill({json:{url:'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=synthetic'}}));
    await page.route('**/api/setup/pkce/callback-manual', route => {
      callbackBody = route.request().postDataJSON();
      return route.fulfill({status:503, json:{error:'Permissions still pending'}});
    });
    await page.goto('/');
    await page.locator('#login-username').fill('browser-admin');
    await page.locator('#login-password').fill('Browser-test123!');
    await page.locator('#login-password').press('Enter');
    await expectSignedIn(page);
    await inApp(page, app => { app.renewCreds('Synthetic_Customer'); });
    await page.locator('#confirm-modal-ok').click();
    await page.locator('#pkce-oob-input').fill('https://login.microsoftonline.com/common/oauth2/nativeclient?code=synthetic-code&state=synthetic');
    await page.locator('#pkce-submit').click();
    await expect(page.locator('#setup-log')).toContainText('Permissions still pending');
    expect(wipes).toBe(0);
    expect(callbackBody.renew_customer_id).toBe('Synthetic_Customer');
    await page.locator('#pkce-restart').click();
    await page.locator('#pkce-oob-input').fill('https://login.microsoftonline.com/common/oauth2/nativeclient?code=second-code&state=synthetic');
    await page.locator('#pkce-submit').click();
    await expect(page.locator('#setup-log')).toContainText('Permissions still pending');
    expect(callbackBody.renew_customer_id).toBe('Synthetic_Customer');
  });

  test(`failed customer registration never shows setup complete (${language})`, async ({page}) => {
    await page.addInitScript(lang => {
      localStorage.setItem('onboarding_done', '1');
      localStorage.setItem('ui_lang', lang);
    }, language);
    let registers = 0;
    await page.route('**/api/setup/pkce/start', route => route.fulfill({json:{url:'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=synthetic'}}));
    await page.route('**/api/setup/pkce/callback-manual', route => route.fulfill({json:{ok:true}}));
    await page.route('**/api/customers/register', route => {
      registers++;
      return route.fulfill({status:503, json:{error:'Customer save failed'}});
    });
    await page.goto('/');
    await page.locator('#login-username').fill('browser-admin');
    await page.locator('#login-password').fill('Browser-test123!');
    await page.locator('#login-password').press('Enter');
    await expectSignedIn(page);
    await inApp(page, app => app.startSetup());
    await page.locator('#pkce-oob-input').fill('https://login.microsoftonline.com/common/oauth2/nativeclient?code=synthetic-code&state=synthetic');
    await page.locator('#pkce-submit').click();
    await expect(page.locator('#setup-log')).toContainText('Customer save failed');
    await expect(page.locator('#setup-result-area .alert-success')).toHaveCount(0);
    await expect(page.locator('#pkce-restart')).toBeVisible();
    await expect(page.locator('#pkce-oob-input')).toHaveValue('');
    expect(registers).toBe(1);
  });

  test(`setup shows connection failure, prevents duplicate submission and supports new sign-in (${language})`, async ({page}) => {
    await page.addInitScript(lang => {
      localStorage.setItem('onboarding_done', '1');
      localStorage.setItem('ui_lang', lang);
    }, language);
    let starts = 0;
    let submissions = 0;
    let releaseFirst;
    const firstResponse = new Promise(resolve => { releaseFirst = resolve; });
    const error = language === 'en'
      ? 'The server could not connect to Microsoft. Check DNS and network, then retry Complete Setup.'
      : 'Serveren kunne ikke koble til Microsoft. Kontroller DNS og nettverk, og prøv Fullfør oppsett igjen.';
    await page.route('**/api/setup/pkce/start', route => {
      starts++;
      return route.fulfill({json:{url:'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=synthetic-' + starts}});
    });
    await page.route('**/api/setup/pkce/callback-manual', async route => {
      submissions++;
      if (submissions === 1) {
        await firstResponse;
        await route.fulfill({status:503, json:{ok:false,error,error_key:'err_setup_pkce_connect',restart_required:false}});
      } else {
        await route.fulfill({json:{ok:true}});
      }
    });
    await page.route('**/api/customers/register', route => route.fulfill({json:{customer_id:'Synthetic_Customer'}}));
    await page.goto('/');
    await page.locator('#login-username').fill('browser-admin');
    await page.locator('#login-password').fill('Browser-test123!');
    await page.locator('#login-password').press('Enter');
    await expectSignedIn(page);
    await inApp(page, app => app.startSetup());
    const submit = page.locator('#pkce-submit');
    const restart = page.locator('#pkce-restart');
    await expect(submit).toBeVisible();
    await page.locator('#pkce-oob-input').fill('https://login.microsoftonline.com/common/oauth2/nativeclient?code=synthetic-code&state=synthetic-1');
    try {
      await submit.click();
      await expect(submit).toBeDisabled();
      await expect(restart).toBeDisabled();
      // Even a second programmatically dispatched event cannot send twice.
      await submit.dispatchEvent('click');
      expect(submissions).toBe(1);
    } finally {
      releaseFirst();
    }
    await expect(page.locator('#setup-log')).toContainText(error);
    await expect(page.locator('[data-click-handler="retryToast"]')).toHaveCount(0);
    await expect(submit).toBeEnabled();
    await expect(restart).toBeEnabled();
    // Retrying here runs the full setup flow, not an orphaned API-only retry.
    await submit.click();
    await expect(page.locator('#setup-result-area')).toContainText(language === 'en' ? 'Setup complete' : 'Oppsett fullført');
    await expect(page.locator('#pkce-oob-input')).toHaveValue('');
    expect(submissions).toBe(2);
    await inApp(page, app => app.startSetup());
    await expect(page.locator('#pkce-url-out')).toHaveValue(/state=synthetic-2/);
    await page.locator('#pkce-oob-input').fill('stale input');
    await restart.click();
    await expect(page.locator('#pkce-url-out')).toHaveValue(/state=synthetic-3/);
    await expect(page.locator('#pkce-oob-input')).toHaveValue('');
  });
}
