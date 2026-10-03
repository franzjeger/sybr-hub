// The application CSP runs no inline event handler (script-src-attr 'none').
// Every control names a registered handler in a data-*-handler attribute
// instead, dispatched by app-handlers.js. These tests walk the interface with the real
// policy and fail on any CSP violation, on a control naming a handler nobody
// registered, and on an uncaught error; and they click at least one migrated
// control per view to show the dispatcher reaches it.
const {test, expect} = require('@playwright/test');
const { inApp, expectSignedIn } = require('./app.cjs');

const PASSWORD = 'Browser-test123!';

// Records what the policy blocks and what goes wrong, from before the first
// script runs, so nothing that happens at load time is missed.
async function watch(page) {
  const problems = [];
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
    window.__cspViolations = [];
    document.addEventListener('securitypolicyviolation', event => {
      window.__cspViolations.push(
        `${event.violatedDirective} blocked ${event.blockedURI || 'inline'} ` +
        `at ${event.sourceFile}:${event.lineNumber} ${event.sample || ''}`.trim());
    });
  });
  page.on('console', message => {
    const text = message.text();
    if (message.type() === 'error' && /Content Security Policy|No UI handler registered/.test(text)) {
      problems.push('console: ' + text);
    }
  });
  page.on('pageerror', error => problems.push('uncaught: ' + error.message));
  return {
    async assertClean() {
      const violations = await page.evaluate(() => window.__cspViolations.slice());
      expect([...violations, ...problems]).toEqual([]);
    },
    async reset() {
      await page.evaluate(() => { window.__cspViolations.length = 0; });
      problems.length = 0;
    },
  };
}

async function login(page, username = 'browser-admin') {
  await page.goto('/');
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(PASSWORD);
  // Enter goes through the registered keydown handler on the password field.
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

// Clicks a control the way a user's click reaches it, even when it sits in a
// closed dropdown: a real click event, dispatched on the element.
async function activate(locator) {
  await locator.first().evaluate(el => el.click());
}

async function openView(page, view) {
  await activate(page.locator(`[data-click-handler="showView"][data-view="${view}"]`));
  await expect(page.locator('#view-' + view)).toHaveClass(/\bactive\b/);
}

test('the application policy allows no inline event handler', async ({page}) => {
  const response = await page.goto('/');
  const csp = response.headers()['content-security-policy'];
  expect(csp).toContain("script-src-attr 'none'");
  expect(csp).not.toContain("'unsafe-inline'; style-src-attr");
  expect(csp).toMatch(/script-src 'self';/);
});

test('an injected inline handler does not run, and the violation is seen', async ({page}) => {
  const monitor = await watch(page);
  await login(page);
  await monitor.assertClean();
  await page.evaluate(() => {
    const host = document.createElement('div');
    host.id = 'inline-fixture';
    host.innerHTML = '<button onclick="globalThis.inlineRan = true">inline</button>';
    document.body.appendChild(host);
  });
  await page.locator('#inline-fixture button').click();
  expect(await page.evaluate(() => globalThis.inlineRan)).toBeUndefined();
  // The watcher is what the other tests rely on; prove it notices.
  await expect.poll(() => page.evaluate(() => window.__cspViolations.length)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__cspViolations.join('\n'))).toContain('script-src-attr');
});

test('every main view opens through the navigation without a policy violation', async ({page}) => {
  test.setTimeout(90000);
  const monitor = await watch(page);
  await login(page);
  // Through the control that opens it where the markup has one (the top
  // bar, Verktøy, a page's own links); the rest are reached from a customer
  // or a dialog, and are opened the way those do.
  const views = ['overview', 'customers', 'network', 'docs', 'logs', 'hosts', 'ssh', 'vpn', 'tailscale',
    'pentest', 'billing', 'provision', 'ai', 'browser', 'setup', 'admin'];
  for (const view of views) {
    const control = page.locator(`[data-click-handler="showView"][data-view="${view}"]`);
    if (await control.count()) await activate(control);
    // Administrasjon opens from the avatar menu.
    else if (view === 'admin') await activate(page.locator('[data-click-handler="avatarOpenAdmin"]'));
    else await inApp(page, (app, v) => app.showView(v), view);
    await expect(page.locator('#view-' + view)).toHaveClass(/\bactive\b/);
    // Let the view's loaders render what they build. Some views poll, so the
    // network never goes idle; the spinners going away is the signal.
    await expect(page.locator('#view-' + view + ' .loader:visible')).toHaveCount(0, {timeout: 10000});
  }
  // The customer page's tabs, each opened from its tab bar.
  await page.evaluate(() => { location.hash = '#/customer/Browser_Beta'; });
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  for (const tab of ['funn', 'audit', 'policyer', 'vurderinger', 'nettverk', 'tilgang', 'detaljer']) {
    await page.locator('#cust-tab-' + tab).click();
    await expect(page.locator('#cust-panel-' + tab)).toBeVisible();
    await expect(page.locator('#cust-panel-' + tab + ' .loader:visible')).toHaveCount(0, {timeout: 10000});
  }
  await monitor.assertClean();
});

// ── One click (at least) per migrated view ───────────────────────────────────
// A shared signed-in page, moved between views. Each test clicks controls that
// used to carry inline handlers and checks what they did, then that nothing was
// blocked or broke on the way.

test.describe('migrated controls, view by view', () => {
  test.describe.configure({mode: 'serial'});
  let page;
  let monitor;

  test.beforeAll(async ({browser}, testInfo) => {
    const context = await browser.newContext({baseURL: testInfo.project.use.baseURL});
    page = await context.newPage();
    monitor = await watch(page);
    await login(page);
  });

  test.afterEach(async () => {
    await monitor.assertClean();
  });

  test.afterAll(async () => {
    await page.context().close();
  });

  test('header: avatar menu, the Konto dialog and its backdrop', async () => {
    await page.locator('#avatar-btn').click();
    await expect(page.locator('#avatar-menu')).toHaveClass(/\bopen\b/);
    // The item closes the menu before it acts: toggleAvatarMenu stopped its
    // own click from reaching the document listener, and still must.
    await page.locator('#avatar-menu [data-click-handler="avatarOpenAccount"]').click();
    await expect(page.locator('#avatar-menu')).not.toHaveClass(/\bopen\b/);
    await expect(page.locator('#account-modal')).toHaveClass(/\bopen\b/);
    await expect(page.locator('#input-language')).toHaveValue('no');
    await page.locator('#account-modal').click({position: {x: 5, y: 5}});
    await expect(page.locator('#account-modal')).not.toHaveClass(/\bopen\b/);
  });

  test('command palette: an item runs its action', async () => {
    await activate(page.locator('[data-click-handler="toggleCommandPalette"]'));
    await expect(page.locator('#cmd-palette')).toBeVisible();
    await page.locator('#cmd-input').fill('Integrasjoner');
    const item = page.locator('#cmd-results [data-click-handler="runCommandPaletteItem"]').first();
    await item.click();
    await expect(page.locator('#cmd-palette')).toBeHidden();
    await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
    await expect(page.locator('#admin-pane-integrations')).toBeVisible();
  });

  test('toasts close from their button', async () => {
    await inApp(page, app => { app.showToast('csp-test toast', 'info', 0); });
    const toast = page.locator('.toast', {hasText: 'csp-test toast'});
    await toast.locator('[data-click-handler="dismissToast"]').click();
    await expect(toast).toHaveCount(0);
  });

  test('Administrasjon: the rail switches panes and the customer-access panel opens and closes', async () => {
    await page.locator('#avatar-btn').click();
    await page.locator('#avatar-menu [data-click-handler="avatarOpenAdmin"]').click();
    await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
    await page.locator('#admin-rail [data-pane="users"]').click();
    await expect(page.locator('#admin-pane-users')).toBeVisible();
    expect(await page.evaluate(() => location.hash)).toBe('#/admin/users');
    const access = page.locator('#admin-pane-users [data-click-handler="editUserCustomers"]').first();
    await expect(access).toBeVisible();
    await access.click();
    const panel = page.locator('[id^="rbac-panel-"]');
    await expect(panel).toHaveCount(1);
    await panel.locator('[data-click-handler="removeElement"]').click();
    await expect(panel).toHaveCount(0);
    await page.locator('#admin-rail [data-pane="system"]').click();
    await expect(page.locator('#admin-pane-system')).toBeVisible();
    await expect(page.locator('#admin-pane-users')).toBeHidden();
  });

  test('overview: tabs, the attention filter, sorting, and the row menu does not open the row', async () => {
    await openView(page, 'overview');
    await page.locator('#view-overview .dash-tab-btn[data-tab="dash-customers"]').click();
    const table = page.locator('.customer-overview-table');
    await expect(table).toBeVisible();
    await page.locator('.attn-strip .attn-action').click();
    await expect(page.locator('#overview-attention-badge')).toBeVisible();
    await page.locator('#overview-active-filters [data-click-handler="dashClearAllFilters"]').click();
    await expect(page.locator('#overview-active-filters')).toBeHidden();
    await page.locator('th[data-click-handler="sortOverview"][data-sort="customer_name"]').click();
    await expect(page.locator('th[data-click-handler="sortOverview"][data-sort="customer_name"]')).toContainText(/[▲▼]/);
    const row = table.locator('tbody tr', {hasText: 'Browser Beta'});
    await row.locator('[data-click-handler="dashToggleRowActions"]').click();
    await expect(row.locator('.row-actions-menu')).toBeVisible();
    await expect(page.locator('#view-overview')).toHaveClass(/\bactive\b/);
    // The menu's own entry opens the customer, once.
    await row.locator('[data-click-handler="dashRowDetails"]').click();
    await expect(page.locator('#view-customer-detail')).toHaveClass(/\bactive\b/);
    await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  });

  test('customer page: the breadcrumb link opens Customers without following "#"', async () => {
    const crumb = page.locator('a[href="#"][data-click-handler="showView"][data-view="customers"]').first();
    await expect(crumb).toBeVisible();
    await crumb.click();
    await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
    expect(await page.evaluate(() => location.hash)).toBe('#/customers');
  });

  test('customers: search filters, the star does not open the card, the card does', async () => {
    await openView(page, 'customers');
    const card = page.locator('#customers-content .card-clickable', {hasText: 'Browser Alpha'});
    await expect(card).toBeVisible();
    await page.locator('#customers-search').fill('Browser Alpha');
    await expect(page.locator('#customers-content .card-clickable', {hasText: 'Browser Beta'})).toHaveCount(0);
    const favorites = () => page.evaluate(() => JSON.parse(localStorage.getItem('sybr_favorites') || '[]').length);
    const before = await favorites();
    await card.locator('[data-click-handler="customerCardToggleFavorite"]').click();
    await expect.poll(favorites).toBe(before + 1);
    await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
    // Back as it was for the other tests.
    await page.locator('#customers-content .card-clickable', {hasText: 'Browser Alpha'})
      .locator('[data-click-handler="customerCardToggleFavorite"]').click();
    await expect.poll(favorites).toBe(before);
    await page.locator('#customers-search').fill('');
    await page.locator('#customers-content .card-clickable', {hasText: 'Browser Beta'}).click();
    await expect(page.locator('#view-customer-detail')).toHaveClass(/\bactive\b/);
  });

  test('runs: a run without evidence files offers the summary report', async () => {
    // The fixture's run holds metrics and no evidence files: it is listed on
    // the Audit tab, and its button opens the summary report.
    await page.evaluate(() => { location.hash = '#/customer/Browser_Beta/audit'; });
    const summary = page.locator('#view-history [data-click-handler="openCustomerSummary"]');
    await expect(summary).toHaveCount(1);
    const [popup] = await Promise.all([page.waitForEvent('popup'), summary.click()]);
    expect(new URL(popup.url()).pathname).toBe('/api/reports/customer-summary/Browser_Beta');
    await popup.close();
  });

  test('network: the sub-tabs switch', async () => {
    await openView(page, 'network');
    await page.locator('.net-sub-btn[data-tab="net-audit"]').click();
    await expect(page.locator('#net-audit')).toBeVisible();
    await page.locator('.net-sub-btn[data-tab="net-devices"]').click();
    await expect(page.locator('#net-devices')).toBeVisible();
  });

  test('integrations: a card opens its settings', async () => {
    await activate(page.locator('[data-click-handler="avatarOpenAdmin"]'));
    await page.locator('#admin-rail [data-pane="integrations"]').click();
    await expect(page.locator('#admin-pane-integrations')).toBeVisible();
    await page.locator('[data-click-handler="toggleIntegConfig"][data-config="webhook-config"]').click();
    await expect(page.locator('#webhook-config')).toBeVisible();
    await page.locator('[data-click-handler="toggleIntegConfig"][data-config="webhook-config"]').click();
    await expect(page.locator('#webhook-config')).toBeHidden();
  });

  test('hosts: the add form reacts to the device type and cancels', async () => {
    await openView(page, 'hosts');
    await page.locator('#view-hosts [data-click-handler="hostsAdd"]').click();
    await page.locator('#host-devtype').selectOption('windows');
    await expect(page.locator('#host-username')).toHaveValue('administrator');
    await page.locator('#view-hosts [data-click-handler="hostsLoad"]').first().click();
    await expect(page.locator('#host-devtype')).toHaveCount(0);
  });

  test('VPN: the new-profile form follows the protocol and cancels', async () => {
    await openView(page, 'vpn');
    await page.locator('#view-vpn [data-click-handler="vpnShowCreate"]').click();
    const fields = page.locator('#vpn-create-fields');
    const protocols = await page.locator('#vpn-create-protocol option').evaluateAll(o => o.map(x => x.value));
    await page.locator('#vpn-create-protocol').selectOption(protocols[protocols.length - 1]);
    const last = await fields.innerHTML();
    await page.locator('#vpn-create-protocol').selectOption(protocols[0]);
    await expect.poll(() => fields.innerHTML()).not.toBe(last);
    await page.locator('#view-vpn [data-click-handler="vpnLoadProfiles"]').first().click();
    await expect(page.locator('#vpn-create-protocol')).toHaveCount(0);
  });

  test('SSH: the key list and the command form open', async () => {
    await openView(page, 'ssh');
    await page.locator('#view-ssh [data-click-handler="sshShowExec"]').click();
    await expect(page.locator('#ssh-exec-cmd')).toBeVisible();
    await page.locator('#view-ssh [data-click-handler="sshShowKeys"]').first().click();
    await expect(page.locator('#view-ssh [data-click-handler="sshGenKey"]')).toBeVisible();
  });

  test('TLS: a tab of Nettverk; checking with no endpoint says so', async () => {
    await openView(page, 'network');
    await page.locator('.net-sub-btn[data-tab="net-tls"]').click();
    await expect(page.locator('#tls-single-result')).toBeEmpty();
    await page.locator('#net-tls [data-click-handler="tlsCheckSingle"]').click();
    await expect(page.locator('#tls-single-result')).not.toBeEmpty();
  });

  test('Audit tab: the section chooser opens and a section toggles', async () => {
    await page.evaluate(() => { location.hash = '#/customer/Browser_Beta/audit'; });
    const toggle = page.locator('#scope-panel [data-click-handler="toggleScopePanel"]');
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.locator('#scope-body')).toBeVisible();
    const section = page.locator('#scope-sections input[data-section]').first();
    await expect(section).toBeVisible();
    const summary = page.locator('#scope-summary');
    const before = await summary.textContent();
    // Each change goes through onScopeChange; twice leaves the saved scope as it was.
    await section.click();
    await expect(summary).not.toHaveText(before);
    await section.click();
    await expect(summary).toHaveText(before);
    await toggle.click();
    await expect(page.locator('#scope-body')).toBeHidden();
  });

  test('Hjelp: the changelog opens, not the repository notes', async () => {
    await page.locator('#avatar-btn').click();
    await page.locator('#avatar-menu [data-click-handler="avatarOpenHelp"]').click();
    await expect(page.locator('#view-docs')).toHaveClass(/\bactive\b/);
    const content = page.locator('#docs-repo-content');
    // The one document on offer opens by itself; with nothing to choose
    // between there is no list.
    await expect(content.locator('h1').first()).toHaveText('Endringslogg');
    await expect(page.locator('#docs-repo-tree')).toBeHidden();
    await expect(content).not.toContainText(/Kunne ikke/);
    await expect(page.locator('#view-docs')).not.toContainText(/ARCHITECTURE|CRITICAL REVIEW/);
  });
});
