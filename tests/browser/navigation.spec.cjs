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
