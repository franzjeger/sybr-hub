// The interface is a graph of ES modules (app/web/static/main.js and what it
// imports). A module that fails to load, an import naming an export that is
// not there, or a module reading another's state before that one has run
// takes down the whole page, or one view, without a word in the markup. This
// walks every top-level view, every customer tab and the phone's Mer sheet,
// through the controls a person uses, and fails on any console error,
// uncaught error or failed request for a script.
const { test, expect } = require('@playwright/test');
const { inApp, expectSignedIn, MODULES } = require('./app.cjs');

const PASSWORD = 'Browser-test123!';

function watch(page) {
  const problems = [];
  const scripts = new Map();   // module URL -> number of times fetched
  page.on('console', message => {
    if (message.type() !== 'error') return;
    // The browser logs every 4xx answer as a console error. The signed-out
    // start (/auth/me, /auth/refresh) answers 401 by design; a script's
    // failure is caught below, by its response.
    const where = message.location().url || '';
    if (/^Failed to load resource/.test(message.text()) && new URL(where, 'http://x').pathname.startsWith('/api/')) return;
    problems.push('console: ' + message.text() + (where ? ' (' + where + ')' : ''));
  });
  page.on('pageerror', error => problems.push('uncaught: ' + error.message));
  page.on('requestfailed', request => {
    if (/\.js(\?|$)/.test(request.url())) problems.push('failed: ' + request.url() + ' ' + request.failure().errorText);
  });
  page.on('response', response => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/static/') || !url.pathname.endsWith('.js')) return;
    if (response.status() >= 400) problems.push(`HTTP ${response.status()}: ${url.pathname}${url.search}`);
    scripts.set(url.pathname + url.search, (scripts.get(url.pathname + url.search) || 0) + 1);
  });
  return {problems, scripts};
}

async function login(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

// A real click event on the control, also when it sits in a closed menu.
async function activate(locator) {
  await locator.first().evaluate(el => el.click());
}

async function settled(page, root) {
  await expect(page.locator(root + ' .loader:visible')).toHaveCount(0, {timeout: 10000});
}

test('every module loads once, from the versioned URL the shell names', async ({page}) => {
  const {problems, scripts} = watch(page);
  await login(page);
  const entry = await page.locator('script[type="module"]').getAttribute('src');
  const version = new URL(entry, 'http://x').search;
  expect(version).toMatch(/^\?v=[0-9a-f]{12}$/);
  // The specs' helper reaches the same copies: importing every module again
  // fetches nothing new.
  await inApp(page, app => Object.keys(app).length);
  // Ours, not the vendored libraries or theme-init.js (a classic script in <head>).
  const loaded = [...scripts.keys()].filter(url => !/^\/static\/(vendor\/|guacamole|theme-init)/.test(url));
  const expected = ['main.js', ...MODULES].map(name => '/static/' + name + version).sort();
  expect(loaded.sort()).toEqual(expected);
  for (const url of loaded) expect(scripts.get(url), url).toBe(1);
  expect(problems).toEqual([]);
});

test('every view, customer tab and Administrasjon pane opens without an error', async ({page}) => {
  test.setTimeout(120000);
  const {problems} = watch(page);
  await login(page);

  // The top bar and Verktøy.
  for (const view of ['overview', 'customers', 'network', 'vpn', 'hosts', 'terminal', 'ssh', 'browser',
    'tailscale', 'pentest', 'provision', 'billing', 'ai', 'logs']) {
    await activate(page.locator(`[data-click-handler="showView"][data-view="${view}"]`));
    await expect(page.locator('#view-' + view)).toHaveClass(/\bactive\b/);
    await settled(page, '#view-' + view);
  }
  // Hjelp, from the avatar menu.
  await page.locator('#avatar-btn').click();
  await page.locator('#avatar-menu [data-click-handler="avatarOpenHelp"]').click();
  await expect(page.locator('#view-docs')).toHaveClass(/\bactive\b/);
  await settled(page, '#view-docs');
  // Their tabs.
  await activate(page.locator('[data-click-handler="showView"][data-view="network"]'));
  for (const tab of ['net-devices', 'net-fortigates', 'net-unifi', 'net-audit', 'net-tls']) {
    await page.locator(`.net-sub-btn[data-tab="${tab}"]`).click();
    await expect(page.locator('#' + tab)).toBeVisible();
    await settled(page, '#' + tab);
  }
  await activate(page.locator('[data-click-handler="showView"][data-view="billing"]'));
  for (const tab of ['dash-renewals', 'dash-costs', 'dash-domains']) {
    await page.locator(`#view-billing .tab[data-tab="${tab}"]`).click();
    await settled(page, '#view-billing');
  }
  await activate(page.locator('[data-click-handler="showView"][data-view="overview"]'));
  for (const tab of ['dash-customers', 'dash-alerts']) {
    await page.locator(`#view-overview .tab[data-tab="${tab}"]`).click();
    await settled(page, '#view-overview');
  }
  // Views reached from another page: RDP from a host, a new customer from Kunder.
  await page.evaluate(() => { location.hash = '#/rdp'; });
  await expect(page.locator('#view-rdp')).toHaveClass(/\bactive\b/);
  await page.evaluate(() => { location.hash = '#/setup'; });
  await expect(page.locator('#view-setup')).toHaveClass(/\bactive\b/);

  // Administrasjon, from the avatar menu, and each pane of its rail.
  await page.locator('#avatar-btn').click();
  await page.locator('#avatar-menu [data-click-handler="avatarOpenAdmin"]').click();
  await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
  for (const pane of ['integrations', 'alerts', 'users', 'modules', 'branding', 'storage', 'system']) {
    await page.locator(`#admin-rail [data-pane="${pane}"]`).click();
    await expect(page.locator('#admin-pane-' + pane)).toBeVisible();
    await settled(page, '#admin-pane-' + pane);
  }

  // The customer page, from Kunder, and each of its tabs.
  await activate(page.locator('[data-click-handler="showView"][data-view="customers"]'));
  await page.locator('#customers-content .card-clickable', {hasText: 'Browser Beta'}).click();
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  for (const tab of ['funn', 'audit', 'policyer', 'vurderinger', 'nettverk', 'tilgang', 'detaljer']) {
    await page.locator('#cust-tab-' + tab).click();
    await expect(page.locator('#cust-panel-' + tab)).toBeVisible();
    await settled(page, '#cust-panel-' + tab);
    await expect(page).toHaveURL(new RegExp('#/customer/Browser_Beta' + (tab === 'funn' ? '$' : '/' + tab + '$')));
  }

  // The command palette and the keyboard.
  await page.keyboard.press('Control+k');
  await expect(page.locator('#cmd-palette')).toBeVisible();
  await page.locator('#cmd-input').fill('Kunder');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
  // Shortcuts other than Ctrl+K wait while a field has focus.
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press('Control+1');
  await expect(page.locator('#view-overview')).toHaveClass(/\bactive\b/);
  await page.keyboard.press('?');
  await expect(page.locator('#shortcuts-modal')).toHaveClass(/\bopen\b/);
  await page.keyboard.press('Escape');

  // Back and forward walk the views it went through.
  await page.goBack();
  await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
  await page.goForward();
  await expect(page.locator('#view-overview')).toHaveClass(/\bactive\b/);

  expect(problems).toEqual([]);
});

test('on a phone, the bottom bar and the Mer sheet open their views without an error', async ({page}) => {
  await page.setViewportSize({width: 375, height: 812});
  const {problems} = watch(page);
  await login(page);
  await page.locator('#bottom-nav [data-click-handler="showView"][data-view="customers"]').click();
  await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
  for (const view of ['network', 'vpn', 'hosts', 'tailscale', 'pentest', 'provision', 'billing', 'ai', 'docs']) {
    await page.locator('#bottom-nav [data-click-handler="openMoreSheet"]').click();
    await page.locator(`[data-click-handler="moreSheetShowView"][data-view="${view}"]`).click();
    await expect(page.locator('#view-' + view)).toHaveClass(/\bactive\b/);
    await settled(page, '#view-' + view);
  }
  await page.locator('#bottom-nav [data-click-handler="openMoreSheet"]').click();
  await page.locator('[data-click-handler="moreSheetOpenAdmin"]').click();
  await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
  expect(problems).toEqual([]);
});
