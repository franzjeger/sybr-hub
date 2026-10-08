// The RMM deep-link on the customer's Tilgang tab (TODO D19). Datto RMM is not
// reachable from a test, so the devices answer is routed: what is tested is
// that the page offers a Web Remote button for a matched device and nothing
// else, that the button opens Datto's own link in a new tab with
// rel="noopener noreferrer", and that no key or token rides in it.
const { test, expect } = require('@playwright/test');
const { expectSignedIn, inApp } = require('./app.cjs');

const REMOTE = 'https://rmm.example/csm/remote/d1';

async function login(page, {language = 'no', theme = 'light'} = {}) {
  await page.addInitScript(([lang, look]) => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', lang);
    localStorage.setItem('sybr-theme', look);
  }, [language, theme]);
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

async function alphaId(page) {
  const r = await page.request.get('/api/dashboard/overview');
  return (await r.json()).customers.find(c => c.customer_name === 'Browser Alpha').customer_id;
}

const DEVICES = {
  status: 'ok',
  provider: 'Datto RMM',
  site: {uid: 'site-a', name: 'Kunde A site'},
  audit_date: '2026-10-01_120000',
  matched: 1,
  devices: [
    {name: 'PC-01', os: 'Windows', sources: ['intune', 'entra'], match: 'matched', matched_by: 'hostname',
      candidates: 0, online: true, web_remote_url: REMOTE},
    {name: 'PC-02', os: 'Windows', sources: ['intune'], match: 'ambiguous', matched_by: '',
      candidates: 2, online: null, web_remote_url: ''},
    {name: 'PC-03', os: 'Windows', sources: ['entra'], match: 'not_found', matched_by: '',
      candidates: 0, online: null, web_remote_url: ''},
  ],
};

async function routeDevices(page, body) {
  await page.route(url => /^\/api\/rmm\/devices\/[^/]+$/.test(new URL(url).pathname),
    route => route.fulfill({json: body}));
}

async function openAccess(page, id) {
  await page.goto('/#/customer/' + encodeURIComponent(id) + '/tilgang');
  await expect(page.locator('#cust-panel-tilgang')).toBeVisible();
}

test.afterEach(async ({page}) => {
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

test('a matched device opens Datto Web Remote in a new tab, and only a matched one', async ({page, context}) => {
  await login(page);
  const id = await alphaId(page);
  await routeDevices(page, DEVICES);
  // The new tab must not leave for the internet; the fake host answers here.
  await context.route('https://rmm.example/**', route => route.fulfill({contentType: 'text/html', body: '<title>remote</title>'}));
  await openAccess(page, id);

  const panel = page.locator('#customer-rmm-panel');
  await expect(panel).toBeVisible();
  await expect(panel).toContainText('Område: Kunde A site');
  await expect(panel).toContainText('1 av 3 enheter');
  const buttons = panel.locator('a', {hasText: 'Åpne WebRemote'});
  await expect(buttons).toHaveCount(1);
  const link = buttons.first();
  await expect(link).toHaveAttribute('href', REMOTE);
  await expect(link).toHaveAttribute('target', '_blank');
  const rel = (await link.getAttribute('rel')).split(/\s+/);
  expect(rel).toEqual(expect.arrayContaining(['noopener', 'noreferrer']));
  expect(await link.getAttribute('href')).not.toMatch(/token|secret|key=/i);
  await expect(link).toHaveAttribute('aria-label', 'Åpne WebRemote for PC-01');

  // The rows without a match fold away, and say why without a button.
  const rest = panel.locator('details.cust-rmm-rest');
  await expect(rest.locator('summary')).toHaveText('Vis 2 enheter uten treff');
  await rest.locator('summary').click();
  await expect(rest).toContainText('Flere treff (2)');
  await expect(rest).toContainText('Ikke funnet');
  await expect(rest.locator('a')).toHaveCount(0);

  const [popup] = await Promise.all([context.waitForEvent('page'), link.click()]);
  await popup.waitForLoadState();
  expect(popup.url()).toBe(REMOTE);
  // noopener: the remote tab cannot reach back into the Hub.
  expect(await popup.evaluate(() => window.opener)).toBeNull();
  await popup.close();
});

test('nothing to open: no button, and the reason is on the card', async ({page}) => {
  await login(page);
  const id = await alphaId(page);
  await routeDevices(page, {...DEVICES, matched: 0, devices: DEVICES.devices.slice(1)});
  await openAccess(page, id);

  const panel = page.locator('#customer-rmm-panel');
  await expect(panel).toContainText('0 av 2 enheter');
  await expect(panel.locator('a')).toHaveCount(0);
  // With nothing to open the unmatched rows are the answer, not folded away.
  await expect(panel.locator('details')).toHaveCount(0);
  await expect(panel).toContainText('Flere treff (2)');
});

test('an RMM that is not set up leaves no card, and an unlinked customer is offered the link', async ({page}) => {
  await login(page);
  const id = await alphaId(page);
  await routeDevices(page, {status: 'not_configured'});
  await openAccess(page, id);
  await expect(page.locator('#customer-rmm-panel')).toBeHidden();

  await page.unrouteAll({behavior: 'ignoreErrors'});
  await routeDevices(page, {status: 'not_linked'});
  await page.reload();
  const panel = page.locator('#customer-rmm-panel');
  await expect(panel).toContainText('Kunden er ikke koblet til et område i Datto RMM.');
  await expect(panel.locator('[data-rmm-link]')).toHaveText('Koble til Datto RMM');
});

test('the card reads in English', async ({page}) => {
  await login(page, {language: 'en'});
  const id = await alphaId(page);
  await routeDevices(page, DEVICES);
  await openAccess(page, id);

  const panel = page.locator('#customer-rmm-panel');
  await expect(panel).toContainText('1 of 3 devices');
  await expect(panel.locator('a', {hasText: 'Open WebRemote'})).toHaveCount(1);
  await expect(panel.locator('summary')).toHaveText('Show 2 devices without a match');
});

for (const [name, width, theme] of [['desktop-light', 1280, 'light'], ['desktop-dark', 1280, 'dark'], ['mobile-light', 375, 'light'], ['mobile-dark', 375, 'dark']]) {
  test(`the card fits ${name}`, async ({page}, testInfo) => {
    await page.setViewportSize({width, height: 900});
    await login(page, {theme});
    const id = await alphaId(page);
    await routeDevices(page, DEVICES);
    await openAccess(page, id);
    const panel = page.locator('#customer-rmm-panel');
    await expect(panel.locator('a', {hasText: 'Åpne WebRemote'})).toBeVisible();
    await panel.locator('summary').click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await panel.screenshot({path: testInfo.outputPath(`rmm-card-${name}.png`)});

    // The settings card the credentials go in, opened but not saved.
    await inApp(page, app => { app.openAdmin('integrations'); app.toggleIntegConfig('drmm-config'); });
    const card = page.locator('#drmm-config').locator('xpath=..');
    await expect(page.locator('#drmm-config')).toBeVisible();
    await expect(page.locator('#input-drmm-url')).toHaveAttribute('placeholder', 'https://concord-api.centrastage.net');
    await expect(page.locator('#input-drmm-key')).toHaveAttribute('type', 'password');
    await expect(page.locator('#input-drmm-secret')).toHaveAttribute('type', 'password');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await card.screenshot({path: testInfo.outputPath(`rmm-settings-${name}.png`)});
  });
}
