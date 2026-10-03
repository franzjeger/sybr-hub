// The information architecture: Oversikt, Kunder and Verktøy in the top bar,
// the account and Administrasjon behind the avatar, every Administrasjon pane
// reachable from its rail and by its address.
const { test, expect } = require('@playwright/test');

const PASSWORD = 'Browser-test123!';

async function login(page, username = 'browser-admin') {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await page.goto('/');
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expect.poll(() => page.evaluate(() => !!_currentUser && !!_i18n.no)).toBe(true);
}

// /auth/me answered as a technician's: the role, and the views a technician
// resolves to (app/core/features.py), without signing in as one of the
// shared technician accounts other specs change.
async function seenAsTechnician(page) {
  await page.route('**/api/auth/me', async route => {
    const response = await route.fetch();
    const body = await response.json();
    (body.user || body).role = 'technician';
    const adminViews = ['admin', 'setup', 'logs', 'provision'];
    if (Array.isArray(body.views)) body.views = body.views.filter(v => adminViews.indexOf(v) === -1);
    await route.fulfill({response, json: body});
  });
}

test('the top bar holds Oversikt, Kunder and Verktøy, and nothing else', async ({page}) => {
  await login(page);
  const items = page.locator('#main-nav > .nav-btn:visible, #main-nav > .nav-dropdown:visible > .nav-btn');
  await expect(items).toHaveText(['Oversikt', 'Kunder', 'Verktøy']);
  await expect(page.locator('#nav-overview')).toHaveClass(/\bactive\b/);

  // Verktøy opens on a click, lists the cross-customer tools, and an entry
  // lights Verktøy and names it in the breadcrumb.
  await page.locator('#nav-tools').click();
  const menu = page.locator('#nav-tools-menu');
  await expect(menu).toBeVisible();
  await expect(page.locator('#nav-tools')).toHaveAttribute('aria-expanded', 'true');
  await expect(menu.locator('.navdd-item:visible .navdd-label')).toHaveText([
    'Nettverk', 'VPN', 'Fjerntilgang', 'Tailscale', 'Pentest', 'Provisjonering', 'Lisenser og hosting', 'Sybrt',
  ]);
  await menu.locator('[data-view="tailscale"]').click();
  await expect(menu).toBeHidden();
  await expect(page.locator('#view-tailscale')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#nav-tools')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#breadcrumb-items')).toHaveText(/Verktøy\s*\/\s*Tailscale/);

  // Opened by a click it stays open without the pointer over it, and Escape
  // closes it without choosing.
  await page.locator('#nav-tools').click();
  await page.mouse.move(5, 600);
  await expect(menu).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toBeHidden();
});

test('there is no active-customer bar; the palette lists recent customers and opens their page', async ({page}) => {
  // Its own account: opening a customer makes it the active one, and other
  // specs read browser-admin's.
  await login(page, 'browser-switcher');
  await expect(page.locator('#active-customer-bar')).toHaveCount(0);
  await expect(page.locator('.context-bar')).toHaveCount(0);
  const overview = await (await page.request.get('/api/dashboard/overview')).json();
  const beta = overview.customers.find(c => c.customer_name === 'Browser Beta');
  const alpha = overview.customers.find(c => c.customer_name === 'Browser Alpha');
  await page.evaluate(ids => localStorage.setItem('sybr_recent_customers', JSON.stringify(ids)), [beta.customer_id, alpha.customer_id]);
  await page.locator('.hdr-search').click();
  const results = page.locator('#cmd-results');
  await expect(results).toContainText('Nylige');
  const recent = results.locator('.cmd-item').first();
  await expect(recent).toContainText('Browser Beta');
  await recent.click();
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  // A search finds a customer and opens its page, not a status screen.
  await page.locator('.hdr-search').click();
  await page.locator('#cmd-input').fill('Browser Alpha');
  await page.locator('#cmd-results .cmd-item', {hasText: 'Browser Alpha'}).first().click();
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Alpha');
  expect(await page.evaluate(() => location.hash)).toBe('#/customer/' + encodeURIComponent(alpha.customer_id));
});

test('TLS is a tab of Nettverk, and the old address lands on it', async ({page}) => {
  await login(page);
  await page.evaluate(() => { location.hash = '#/tls'; });
  await expect(page.locator('#view-network')).toHaveClass(/\bactive\b/);
  await expect(page.locator('.net-sub-btn[data-tab="net-tls"]')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#tls-content [data-click-handler="tlsCheckSingle"]')).toBeVisible();
});

test('the avatar menu holds the account, and Administrasjon only for an administrator', async ({browser}) => {
  const admin = await browser.newPage();
  await login(admin);
  await admin.locator('#avatar-btn').click();
  await expect(admin.locator('#avatar-menu .avatar-item:visible .avatar-label')).toHaveText([
    'Konto', 'Tema', 'Snarveier', 'Administrasjon', 'Hjelp', 'Logg ut',
  ]);
  await admin.close();

  const tech = await browser.newPage();
  await seenAsTechnician(tech);
  await login(tech);
  await tech.locator('#avatar-btn').click();
  await expect(tech.locator('#avatar-menu .avatar-item:visible .avatar-label')).toHaveText([
    'Konto', 'Tema', 'Snarveier', 'Hjelp', 'Logg ut',
  ]);
  // Neither the address nor the shortcut opens it for a technician.
  await tech.keyboard.press('Escape');
  await tech.evaluate(() => { location.hash = '#/admin/users'; });
  await expect(tech.locator('#view-admin')).not.toHaveClass(/\bactive\b/);
  await tech.close();
});

test('every Administrasjon pane opens from the rail and from its address', async ({page}) => {
  await login(page);
  await page.locator('#avatar-btn').click();
  await page.locator('#avatar-menu [data-click-handler="avatarOpenAdmin"]').click();
  await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
  const panes = {
    integrations: 'Integrasjoner', alerts: 'Varsler og planlagte oppgaver', users: 'Brukere',
    modules: 'Moduler', branding: 'Branding', storage: 'Lagring og backup', system: 'System',
  };
  for (const [pane, title] of Object.entries(panes)) {
    await page.locator(`#admin-rail [data-pane="${pane}"]`).click();
    await expect(page.locator('#admin-pane-' + pane)).toBeVisible();
    await expect(page.locator('#admin-pane-' + pane + ' .page-title')).toHaveText(title);
    await expect(page.locator(`#admin-rail [data-pane="${pane}"]`)).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('#view-admin .admin-pane:visible')).toHaveCount(1);
    expect(await page.evaluate(() => location.hash)).toBe('#/admin/' + pane);
  }
  // Back walks the panes, and the old Integrasjoner address is a pane.
  await page.goBack();
  await expect(page.locator('#admin-pane-storage')).toBeVisible();
  await page.evaluate(() => { location.hash = '#/integrations'; });
  await expect(page.locator('#admin-pane-integrations')).toBeVisible();
  await expect.poll(() => page.evaluate(() => location.hash)).toBe('#/admin/integrations');
  // Ctrl+, opens it from anywhere.
  await page.evaluate(() => showView('overview'));
  await page.keyboard.press('Control+,');
  await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
});

// ── The customer page ────────────────────────────────────────────────────────
// These open customers, which makes each the account's active customer, so
// they sign in as browser-switcher: other specs read browser-admin's.

const TABS = ['funn', 'audit', 'policyer', 'vurderinger', 'nettverk', 'tilgang', 'detaljer'];

async function openedTab(page, tab) {
  await expect(page.locator('#cust-panel-' + tab)).toBeVisible();
  await expect(page.locator('#cust-tab-' + tab)).toHaveClass(/\bactive\b/);
  await expect(page.locator('#cust-tab-' + tab)).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#view-customer-detail .cust-panel:visible')).toHaveCount(1);
  await expect(page.locator('#cust-tabs .cust-tab.active')).toHaveCount(1);
}

test('Lagring og backup copes with settings that leave the storage paths out', async ({page}) => {
  // The server sends the paths to administrators only. Answered without them
  // (a role changed under an open session), the pane must not print
  // "undefined", and saving another card must not post empty paths, which
  // would reset both folders to the default.
  let posted = null;
  await page.route('**/api/settings', async route => {
    if (route.request().method() === 'POST') {
      posted = route.request().postDataJSON();
      await route.fulfill({json: {ok: true}});
      return;
    }
    const response = await route.fetch();
    const body = await response.json();
    for (const k of Object.keys(body)) if (/^(audit|cert)_dir/.test(k)) delete body[k];
    await route.fulfill({response, json: body});
  });
  await login(page);
  await page.evaluate(() => openAdmin('storage'));
  const pane = page.locator('#admin-pane-storage');
  await expect(pane).toBeVisible();
  await expect(page.locator('#input-audit-dir')).toHaveValue('');
  await expect(page.locator('#settings-current-dir')).toHaveText('');
  await expect(pane).not.toContainText('undefined');
  await page.locator('#admin-rail [data-pane="branding"]').click();
  await page.locator('#admin-pane-branding [data-click-handler="saveSettings"]').click();
  await expect.poll(() => posted).not.toBeNull();
  expect(posted).not.toHaveProperty('audit_dir');
  expect(posted).not.toHaveProperty('cert_dir');
  expect(posted.branding).toBeTruthy();
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

test('the customer page tabs switch in place, and the address carries the tab', async ({page}) => {
  await login(page, 'browser-switcher');
  await page.evaluate(() => { location.hash = '#/customer/Browser_Beta'; });
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  await openedTab(page, 'funn');
  // Mark the page: a tab that reloaded it would build a new head.
  await page.locator('#cust-page-head .cust-head').evaluate(el => { el.dataset.marker = 'kept'; });
  for (const tab of TABS) {
    await page.locator('#cust-tab-' + tab).click();
    await openedTab(page, tab);
    expect(await page.evaluate(() => location.hash)).toBe('#/customer/Browser_Beta' + (tab === 'funn' ? '' : '/' + tab));
  }
  await expect(page.locator('#cust-page-head .cust-head')).toHaveAttribute('data-marker', 'kept');
  // Back and forward walk the tabs, still in place.
  await page.goBack();
  await openedTab(page, 'tilgang');
  await page.goBack();
  await openedTab(page, 'nettverk');
  await page.goForward();
  await openedTab(page, 'tilgang');
  await expect(page.locator('#cust-page-head .cust-head')).toHaveAttribute('data-marker', 'kept');
  // The arrow keys move along the tab list.
  await page.locator('#cust-tab-tilgang').focus();
  await page.keyboard.press('ArrowRight');
  await openedTab(page, 'detaljer');
  // A reload lands on the tab in the address.
  await page.reload();
  await expect.poll(() => page.evaluate(() => typeof _currentUser !== 'undefined' && !!_currentUser)).toBe(true);
  await openedTab(page, 'detaljer');
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
});

test('each old address lands on the tab it became, for the active customer', async ({page}) => {
  await login(page, 'browser-switcher');
  await page.evaluate(() => { location.hash = '#/customer/Browser_Beta'; });
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  const routes = {
    home: 'funn', files: 'detaljer', audit: 'audit', history: 'audit', 'policy-overview': 'policyer',
    // A technician has no tenant grant: the deploy flows are not offered,
    // and their addresses land on Policy-oversikt.
    'policy-deploy': 'policyer', 'baseline-deploy': 'policyer', assessments: 'vurderinger',
  };
  for (const [old, tab] of Object.entries(routes)) {
    await page.evaluate(() => showView('overview'));
    await page.evaluate(h => { location.hash = h; }, '#/' + old);
    await openedTab(page, tab);
    await expect.poll(() => page.evaluate(() => location.hash)).toBe('#/customer/Browser_Beta' + (tab === 'funn' ? '' : '/' + tab));
    if (tab === 'policyer') await expect(page.locator('#view-policy-overview')).toBeVisible();
  }
  // With no customer active, an old address goes to Kunder to choose one.
  await page.route('**/api/customers', async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.active_id = null;
    await route.fulfill({response, json: body});
  });
  // The last tab's loader may still be reading /api/customers from before the
  // route above, and puts the active customer back when it lands; try again
  // until nothing is in flight to do that.
  await expect.poll(async () => {
    await page.evaluate(() => { _customersActiveId = null; showView('overview'); location.hash = '#/audit'; });
    await page.waitForTimeout(300);
    return page.evaluate(() => currentView);
  }).toBe('customers');
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

test('the bell opens Varsler on Oversikt, with the events it used to list', async ({page}) => {
  // The fixture has sent no alerts and logged nothing worth showing, so this
  // page is told about one of each: what the alert engine sent (twice, as it
  // repeats an alert every check) and one event.
  const now = new Date().toISOString();
  await page.route('**/api/alerts/history*', route => route.fulfill({json: {entries: [
    {type: 'ssl_expiry', severity: 'critical', customer: 'Browser Beta', item: 'www.example.com', detail: 'Utløper om 3 dager', sent_at: now},
    {type: 'ssl_expiry', severity: 'critical', customer: 'Browser Beta', item: 'www.example.com', detail: 'Utløper om 4 dager', sent_at: now},
  ], total: 2}}));
  await page.route('**/api/activity-log*', route => route.fulfill({json: {entries: [
    {timestamp: now, action: 'audit_completed', detail: '', customer: 'Browser Beta', user: 'browser-admin'},
    {timestamp: now, action: 'customer_switched', detail: '', customer: 'Browser Beta', user: 'browser-admin'},
  ]}}));
  await login(page);
  await page.evaluate(() => showView('customers'));
  await page.locator('#notif-bell').click();
  await expect(page.locator('#view-overview')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#view-overview .dash-tab-btn[data-tab="dash-alerts"]')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#dash-alerts')).toBeVisible();
  await expect(page.locator('#notif-badge')).toBeHidden();
  const sent = page.locator('#dash-alerts .notif-group-label', {hasText: 'Sendt av automatiske varsler'});
  await expect(sent).toHaveText(/\(1\)/);
  // Switching customer is not news; finishing an audit is.
  await expect(page.locator('#dash-alerts .notif-group-label', {hasText: 'Siste hendelser'})).toHaveText(/\(1\)/);
  // The rule switches are settings, in Administrasjon, not here.
  await expect(page.locator('#dash-alerts input[type="checkbox"]')).toHaveCount(0);
  await page.getByRole('button', {name: 'Endre kanaler'}).click();
  await expect(page.locator('#admin-pane-alerts')).toBeVisible();
});

test('Oversikt leads with who needs attention, without tiles, charts or an integration strip', async ({page}) => {
  await login(page);
  await page.evaluate(() => showView('overview'));
  const rows = page.locator('.customer-overview-table tbody tr');
  await expect(rows.first()).toBeVisible();
  await expect(page.locator('#view-overview canvas, #view-overview .kpi-row')).toHaveCount(0);
  // Nothing in the fixture is failing, so no banner either.
  await expect(page.locator('#integration-health-widget')).toBeHidden();
  // Worst first: the order follows the open findings, and a customer never
  // audited sits above one with only low ones.
  const weights = await page.evaluate(() => Array.from(document.querySelectorAll('.customer-overview-table tbody tr'))
    .map(tr => _findingWeight(_overviewData.customers.find(c => c.customer_id === tr.dataset.customerId))));
  expect(weights).toEqual([...weights].sort((a, b) => b - a));
  await expect(page.locator('.customer-overview-table th', {hasText: 'Åpne funn'})).toContainText('▼');
});

test('Ny kunde is one flow from Kunder: with Microsoft 365 or without', async ({page}) => {
  await login(page);
  await page.locator('#nav-customers').click();
  await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#view-customers').getByRole('button', {name: /Legg til manuelt/})).toHaveCount(0);
  await page.locator('#view-customers [data-click-handler="openNewCustomer"]').click();
  const modal = page.locator('#manual-customer-modal');
  await expect(modal).toBeVisible();
  await expect(modal.locator('.new-cust-choice')).toHaveCount(2);
  await expect(page.locator('#new-cust-form')).toBeHidden();
  await modal.getByRole('button', {name: /Uten Microsoft 365/}).click();
  await expect(page.locator('#new-cust-form')).toBeVisible();
  await expect(page.locator('#manual-cust-name')).toBeFocused();
  await expect(page.locator('#btn-manual-cust-save')).toBeVisible();
  await modal.getByRole('button', {name: 'Avbryt'}).click();
  await expect(modal).toBeHidden();
});

// ── A 375 px phone ───────────────────────────────────────────────────────────

test.describe('on a 375 px phone', () => {
  test.use({viewport: {width: 375, height: 812}});

  const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const tab = (page, name) => page.locator('.bnav-item[data-bnav="' + name + '"]');

  test('the bottom bar holds Oversikt, Kunder, Søk, Varsler and Mer; Søk opens the palette', async ({page}) => {
    await login(page);
    await expect(page.locator('#main-nav')).toBeHidden();
    // The label, not Varsler's unread count beside it.
    await expect(page.locator('.bnav-item:visible > span[data-i18n]')).toHaveText(['Oversikt', 'Kunder', 'Søk', 'Varsler', 'Mer']);
    // The bar carries Varsler, so the header does not carry the bell twice.
    await expect(page.locator('#notif-bell')).toBeHidden();

    await page.locator('#bnav-search').click();
    await expect(page.locator('#cmd-palette')).toBeVisible();
    await expect(page.locator('#cmd-input')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.locator('#cmd-palette')).toBeHidden();
    await expect(tab(page, 'search')).not.toHaveClass(/\bactive\b/);

    // Varsler is Oversikt's Varsler tab and lights its own item; Oversikt
    // goes back to the follow-up list.
    await tab(page, 'alerts').click();
    await expect(page.locator('#dash-alerts')).toBeVisible();
    await expect(tab(page, 'alerts')).toHaveClass(/\bactive\b/);
    await expect(tab(page, 'dashboard')).not.toHaveClass(/\bactive\b/);
    await tab(page, 'dashboard').click();
    await expect(page.locator('#dash-customers')).toBeVisible();
    await expect(tab(page, 'dashboard')).toHaveClass(/\bactive\b/);
    await tab(page, 'customers').click();
    await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
    await expect(tab(page, 'customers')).toHaveClass(/\bactive\b/);
  });

  test('Mer holds Verktøy, Administrasjon and the account', async ({page}) => {
    await login(page);
    await tab(page, 'more').click();
    const sheet = page.locator('#more-sheet');
    await expect(sheet).toBeVisible();
    await expect(sheet.locator('.more-group-title:visible')).toHaveText(['Verktøy', 'Administrasjon', 'Konto']);
    await expect(sheet.locator('[data-click-handler="moreSheetShowView"]:visible > span:nth-child(2)')).toHaveText([
      'Nettverk', 'VPN', 'Fjerntilgang', 'Tailscale', 'Pentest', 'Provisjonering', 'Lisenser og hosting', 'Sybrt', 'Hjelp',
    ]);
    await sheet.locator('[data-click-handler="moreSheetShowView"][data-view="tailscale"]').click();
    await expect(sheet).toBeHidden();
    await expect(page.locator('#view-tailscale')).toHaveClass(/\bactive\b/);
    await expect(tab(page, 'more')).toHaveClass(/\bactive\b/);
    await tab(page, 'more').click();
    await sheet.locator('[data-click-handler="moreSheetOpenAdmin"]').click();
    await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
    await expect(tab(page, 'more')).toHaveClass(/\bactive\b/);
  });

  test('a technician has no Administrasjon in Mer', async ({page}) => {
    await seenAsTechnician(page);
    await login(page);
    await tab(page, 'more').click();
    const sheet = page.locator('#more-sheet');
    await expect(sheet.locator('.more-group-title:visible')).toHaveText(['Verktøy', 'Konto']);
    await expect(sheet.locator('[data-click-handler="moreSheetOpenAdmin"]')).toBeHidden();
  });

  // The customer page changes the active customer, which other specs read
  // from browser-admin, so it signs in as browser-switcher.
  for (const [label, hash, ready, user] of [
    ['Oversikt', '#/overview', '.customer-overview-table tbody tr', 'browser-admin'],
    ['Kunder', '#/customers', '#customers-content .cust-card', 'browser-admin'],
    ['a customer tab', '#/customer/Browser_Beta/audit', '#cust-panel-audit #view-history', 'browser-switcher'],
    ['Administrasjon', '#/admin/integrations', '#admin-pane-integrations', 'browser-admin'],
    ['Varsler', '#/overview', '#dash-alerts-content .notif-toolbar', 'browser-admin'],
  ]) {
    test(`${label} has no sideways scroll`, async ({page}) => {
      await login(page, user);
      await page.evaluate(h => { location.hash = h; }, hash);
      if (label === 'Varsler') await tab(page, 'alerts').click();
      await expect(page.locator(ready).first()).toBeVisible();
      await page.waitForTimeout(300);
      expect(await overflow(page)).toBe(0);
    });
  }
});
