// This changes global settings and runs after all other settings-form specs.
const {test, expect} = require('@playwright/test');
const {inApp, expectSignedIn} = require('./app.cjs');

test('IT Glue Save is visible with write access and persists a key and region across reloads', async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expectSignedIn(page);
  await inApp(page, app => app.openAdmin('integrations'));
  await page.locator('[data-config="itglue-config"]').click();
  const panel = page.locator('#itglue-config');
  const save = panel.locator('[data-click-handler="saveITGlueSettings"]');
  await expect(save).toBeVisible();
  await expect(panel.locator('.readonly-settings-notice')).toBeHidden();
  await page.locator('#input-itglue-key').fill('synthetic-itglue-key');
  await page.locator('#input-itglue-region').selectOption('us');
  const saved = page.waitForResponse(r => r.url().endsWith('/api/settings') && r.request().method() === 'POST');
  await save.click();
  expect((await saved).status()).toBe(200);
  await expect(page.locator('#itglue-save-msg')).toContainText('Lagret');

  await page.reload();
  await expectSignedIn(page);
  await inApp(page, app => app.openAdmin('integrations'));
  await page.locator('[data-config="itglue-config"]').click();
  await expect(page.locator('#input-itglue-key')).toHaveValue('••••••');
  await expect(page.locator('#input-itglue-region')).toHaveValue('us');

  // Region-only saves must preserve the stored secret, not save its mask.
  await page.locator('#input-itglue-region').selectOption('eu');
  await save.click();
  await expect(page.locator('#itglue-save-msg')).toContainText('Lagret');
  await page.reload();
  await expectSignedIn(page);
  await inApp(page, app => app.openAdmin('integrations'));
  await page.locator('[data-config="itglue-config"]').click();
  await expect(page.locator('#input-itglue-key')).toHaveValue('••••••');
  await expect(page.locator('#input-itglue-region')).toHaveValue('eu');
});

test('storage and branding saves preserve concurrent integration and scheduler edits', async ({page}) => {
  await page.addInitScript(() => { localStorage.setItem('onboarding_done','1'); localStorage.setItem('ui_lang','en'); });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expectSignedIn(page);
  await inApp(page, app => app.openAdmin('storage'));
  await expect(page.locator('#input-itglue-region')).toHaveValue('eu');
  await page.request.post('/api/settings', {data:{itglue_region:'us',smtp_server:'concurrent.example.invalid'}});
  await page.request.post('/api/scheduler', {data:{interval_hours:24}});
  for (const pane of ['storage','branding']) {
    await inApp(page, (app,pane) => app.adminShowPane(pane), pane);
    await page.locator('#admin-pane-' + pane + ' [data-click-handler="saveSettings"]').click();
    await expect(page.locator('#admin-pane-' + pane + ' [data-settings-msg]')).toContainText('Saved');
    const settings = (await (await page.request.get('/api/settings')).json());
    expect(settings.itglue_region).toBe('us');
    expect(settings.smtp_server).toBe('concurrent.example.invalid');
    expect((await (await page.request.get('/api/scheduler')).json()).interval_hours).toBe(24);
  }
});
