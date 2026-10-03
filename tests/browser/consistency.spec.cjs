// Screens agree with each other about the same customer, unknown reads as
// unknown, normal states are not errors, and nothing shows a person the
// server's internals. The fixture's Browser Beta has one run whose metrics
// hold no users_no_mfa, no policy snapshot and no evidence files; Browser
// Alpha was never audited. browser-admin can write but has no tenant grant.
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

// The page believes it is a technician's: /auth/me is answered with the
// technician role. Signing in as one of the shared technician accounts would
// collide with specs that enrol them in MFA or switch their customer.
async function seenAsTechnician(page) {
  await page.route('**/api/auth/me', async route => {
    const response = await route.fetch();
    const body = await response.json();
    (body.user || body).role = 'technician';
    // And the views a technician resolves to: the administrator's pages are
    // not among them (app/core/features.py).
    const adminViews = ['admin', 'setup', 'logs', 'provision'];
    if (Array.isArray(body.views)) body.views = body.views.filter(v => adminViews.indexOf(v) === -1);
    await route.fulfill({response, json: body});
  });
}

// This tab's current customer, which the old page names (#/files and the
// rest) open the page of.
async function asBeta(page) {
  await page.evaluate(() => setCurrentCustomer('Browser_Beta'));
}

// Every toast shown from here on, error or not, by its class and text.
async function recordToasts(page) {
  await page.evaluate(() => {
    window.__toasts = [];
    new MutationObserver(records => records.forEach(r => r.addedNodes.forEach(n => {
      if (n.classList && n.classList.contains('toast')) window.__toasts.push(n.className + ': ' + n.textContent.trim());
    }))).observe(document.getElementById('toast-container'), {childList: true});
  });
}

async function overflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

// ── The customer page ────────────────────────────────────────────────────────

test('the Detaljer card says "ukjent" for users without MFA when the run did not count them', async ({page}) => {
  await login(page);
  await page.goto('/#/customer/Browser_Beta');
  const details = page.locator('#cust-details');
  await expect(details).toBeVisible();
  // The finding above it is about an admin without MFA: never a reassuring 0.
  const mfa = details.locator('dt', {hasText: 'Brukere uten MFA'}).locator('xpath=following-sibling::dd[1]');
  await expect(mfa).toHaveText('ukjent');
  await expect(mfa).toHaveClass(/is-unknown/);
  await expect(details.locator('dt', {hasText: 'Brukere'}).first().locator('xpath=following-sibling::dd[1]')).toHaveText('24');
  // The run is named by its date and time, not its folder.
  await expect(details).toContainText('30. september 2026 kl. 12:00');
  await expect(details).not.toContainText('2026-09-30');
});

test('the Sybr Standard panel says once that nothing was assessed, in words, not field names', async ({page}) => {
  await login(page);
  await page.goto('/#/customer/Browser_Beta');
  const panel = page.locator('#cust-standard');
  await expect(panel).toContainText('Ingen krav kunne vurderes');
  // No bare score beside "etterlevelse" when nothing was assessed.
  await expect(panel.locator('.cust-standard-pct')).toHaveCount(0);
  const rows = panel.locator('.cust-standard-table tr');
  await expect(rows.first()).toBeHidden();
  await panel.locator('.cust-standard-details summary').click();
  await expect(rows.first()).toBeVisible();
  await expect(panel).toContainText('Ikke vurdert: MFA-dataene ble ikke samlet inn i denne kjøringen.');
  await expect(panel).not.toContainText(/has_data|\bmfa\.|measured|er ikke satt/);
});

test('the trend card is one line, not an empty chart frame, before a second run', async ({page}) => {
  await login(page);
  await page.goto('/#/customer/Browser_Beta');
  const trend = page.locator('#cust-trend');
  await expect(trend.locator('.cust-trend-empty')).toHaveText('Trenden vises når kunden har minst to kjøringer.');
  await expect(trend.locator('canvas')).toHaveCount(0);
  expect((await trend.boundingBox()).height).toBeLessThan(140);
});

test('the infrastructure card points at Verter and VPN, where hosts are linked', async ({page}) => {
  await login(page);
  // On the customer page's Tilgang tab.
  await page.goto('/#/customer/Browser_Beta/tilgang');
  const infra = page.locator('#customer-infra-panel');
  await expect(infra).not.toContainText('Infrastruktur-seksjonen');
  await infra.getByRole('button', {name: 'Åpne Verter'}).click();
  await expect(page.locator('#view-hosts')).toHaveClass(/\bactive\b/);
});

// ── Other views about the same customer ──────────────────────────────────────

test('the runs on the Audit tab list the run the customer page reports, with a way to a report', async ({page}) => {
  await login(page);
  await page.goto('/#/customer/Browser_Beta/audit');
  const content = page.locator('#history-content');
  await expect(content).not.toContainText('Ingen tidligere kjøringer');
  const row = content.locator('tr', {hasText: '30. september 2026 kl. 12:00'});
  await expect(row).toHaveCount(1);
  await expect(row).toContainText('Bare nøkkeltall');
  await expect(row.getByRole('button', {name: 'Sammendragsrapport'})).toBeVisible();
});

test('Policy-oversikt reads unknown as unknown when no policies were captured', async ({page}) => {
  await login(page);
  await asBeta(page);
  await page.evaluate(() => showView('policy-overview'));
  const standards = page.locator('#po-standards');
  await expect(standards).toContainText('Kundens policyer er ikke samlet inn ennå');
  await expect(standards.locator('.po-unknown').first()).toBeVisible();
  await expect(standards.locator('.po-absent')).toHaveCount(0);
  await expect(standards).not.toContainText('Ikke til stede');
  await expect(standards.locator('.po-std-statuscell-missing')).toHaveCount(0);
});

test('the Audit tab names the last run by date, and the page offers "Kjør audit" once', async ({page}) => {
  await login(page);
  await page.goto('/#/customer/Browser_Beta/audit');
  const idle = page.locator('#audit-idle');
  await expect(idle).toContainText('Siste audit: 30. september 2026 kl. 12:00');
  await expect(page.locator('#view-customer-detail')).not.toContainText('2026-09-30_');
  // One Kjør audit on the page, in its head, and it is live: Beta is a GDAP
  // customer, audited through delegated access.
  const run = page.locator('#view-customer-detail button:visible', {hasText: /^\s*Kjør audit\s*$/});
  await expect(run).toHaveCount(1);
  await expect(page.locator('#cust-run-audit')).toBeEnabled();
  await expect(page.locator('#view-customer-detail')).not.toContainText('ikke M365-tilganger konfigurert');
});

test('the dashboard has no second scoreboard: the Helse tab is gone', async ({page}) => {
  await login(page);
  await page.evaluate(() => showView('overview'));
  await expect(page.locator('.dash-tab-btn[data-tab="dash-customers"]')).toBeVisible();
  await expect(page.locator('.dash-tab-btn[data-tab="dash-health"]')).toHaveCount(0);
});

test('Lisenser og hosting (Domener among them) is part of the billing module', async ({page}) => {
  // Billing off for this page only: the session reports the modules.
  await page.route('**/api/auth/me', async route => {
    const response = await route.fetch();
    const body = await response.json();
    if (Array.isArray(body.modules)) body.modules = body.modules.filter(m => m !== 'billing');
    await route.fulfill({response, json: body});
  });
  await login(page);
  await page.evaluate(() => showView('overview'));
  await expect(page.locator('.dash-tab-btn[data-tab="dash-customers"]')).toBeVisible();
  // Not on Oversikt at all any more, and gone from Verktøy with the module.
  await expect(page.locator('#view-overview .dash-tab-btn[data-tab="dash-domains"]')).toHaveCount(0);
  await expect(page.locator('#nav-tools-menu [data-view="billing"]')).toHaveClass(/gated-hidden/);
  await expect(page.locator('#nav-tools-menu [data-view="network"]')).not.toHaveClass(/gated-hidden/);
});

// ── Normal states are not errors ─────────────────────────────────────────────

test('opening Tailscale without a key shows how to set it up, not an error toast', async ({page}) => {
  await login(page);
  await recordToasts(page);
  await page.evaluate(() => showView('tailscale'));
  const empty = page.locator('#ts-not-configured');
  await expect(empty).toContainText('Tailscale er ikke satt opp');
  await expect.poll(() => page.evaluate(() => window.__toasts)).toEqual([]);
  await empty.getByRole('button', {name: 'Åpne Integrasjoner'}).click();
  await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#admin-pane-integrations')).toBeVisible();
});

test('Rull ut is not offered without the tenant grant, and the old deploy address lands on Policy-oversikt quietly', async ({page}) => {
  await login(page);
  await page.goto('/#/customer/Browser_Beta/policyer');
  await expect(page.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');
  await expect(page.locator('#cust-tab-policyer')).toHaveClass(/\bactive\b/);
  // browser-admin can write but has no tenant grant: Rull ut is hidden by
  // the grant rule itself.
  await expect(page.locator('#cust-deploy')).toBeHidden();
  await recordToasts(page);
  const refused = [];
  page.on('response', r => { if (r.status() === 403) refused.push(r.url()); });
  await page.evaluate(() => { location.hash = '#/policy-deploy'; });
  await expect.poll(() => page.evaluate(() => location.hash)).toBe('#/customer/Browser_Beta/policyer');
  await expect(page.locator('#view-policy-overview')).toBeVisible();
  await expect(page.locator('#view-policy-deploy')).toBeHidden();
  await page.waitForTimeout(500);
  expect(refused).toEqual([]);
  expect(await page.evaluate(() => window.__toasts)).toEqual([]);
});

// ── Nothing internal shown to a person ───────────────────────────────────────

test('the Wiki tab and its load errors are gone from Integrasjoner', async ({page}) => {
  await login(page);
  const missing = [];
  page.on('response', r => { if (r.url().includes('/api/docs/file') && r.status() === 404) missing.push(r.url()); });
  await page.evaluate(() => openAdmin('integrations'));
  await expect(page.locator('#integ-active')).toBeVisible();
  await expect(page.locator('#integ-wiki')).toHaveCount(0);
  await expect(page.locator('#admin-pane-integrations')).not.toContainText('Kunne ikke laste dokumentasjon');
  expect(missing).toEqual([]);
});

test('a technician sees the changelog in Docs, not the API reference', async ({page}) => {
  await seenAsTechnician(page);
  await login(page);
  await page.evaluate(() => showView('docs'));
  await expect(page.locator('#docs-repo-content h1').first()).toHaveText('Endringslogg');
  // The API reference is under Administrasjon › System, not in Hjelp.
  await expect(page.locator('#view-docs')).not.toContainText('REST API');
  await expect(page.locator('#view-docs')).not.toContainText(/ARCHITECTURE|TODO|CRITICAL REVIEW/);
});

test('Administrasjon shows the version, not the host, and only to an admin', async ({page}) => {
  await login(page);
  await page.evaluate(() => openAdmin('system'));
  const admin = page.locator('#view-admin');
  await expect(page.locator('#settings-version-info')).toHaveText(/^Versjon: \d/);
  await expect(admin).not.toContainText(/Python:|Platform:|PID:|Branch:/);
  // The old product name is not a label or a placeholder any more.
  const placeholders = await admin.locator('input[placeholder]').evaluateAll(els => els.map(e => e.placeholder).join(' '));
  expect(placeholders).not.toContain('MSPToolkit');
  await page.locator('#admin-rail [data-pane="storage"]').click();
  await expect(page.locator('#settings-current-dir')).toBeVisible();

  const tech = await page.context().browser().newPage();
  await seenAsTechnician(tech);
  await login(tech);
  // Ctrl+, opens the account's own settings for anyone but an administrator.
  await tech.evaluate(() => openAdmin('storage'));
  await expect(tech.locator('#view-admin')).not.toHaveClass(/\bactive\b/);
  await expect(tech.locator('#account-modal')).toHaveClass(/\bopen\b/);
  await expect(tech.locator('#input-audit-dir')).toBeHidden();
  await expect(tech.locator('#avatar-menu [data-click-handler="avatarOpenAdmin"]')).toBeHidden();
  await tech.close();
});

test('Filer names reports and runs without server paths', async ({page}) => {
  await login(page);
  await asBeta(page);
  await page.evaluate(() => showView('files'));
  await expect(page.locator('#files-rawdata')).toContainText('30. september 2026 kl. 12:00');
  await expect(page.locator('#view-files')).not.toContainText(/\/tmp\/|\/home\/|sybr-browser-/);
});

test('the system account cannot be deleted from Brukere', async ({page}) => {
  await login(page);
  await page.evaluate(() => openAdmin('users'));
  const row = page.locator('#users-list [data-user-id]', {hasText: '@sybr-system'});
  await expect(row).toBeVisible();
  await expect(row.locator('[data-click-handler="deleteUser"]')).toHaveCount(0);
  await expect(row).toContainText('Systemkonto');
  const users = (await (await page.request.get('/api/auth/users')).json()).users;
  const system = users.find(u => u.username === 'sybr-system');
  const refused = await page.request.delete('/api/auth/users/' + system.id);
  expect(refused.status()).toBe(400);
  expect((await refused.json()).error_key).toBe('err_auth_cannot_delete_system');
});

test('buttons and the top nav use the page font', async ({page}) => {
  await login(page);
  for (const selector of ['.nav-btn', '.hdr-search', '.dash-tab-btn']) {
    const font = await page.locator(selector).first().evaluate(el => getComputedStyle(el).fontFamily);
    expect(font).toContain('Cairo');
  }
});

// ── A 375 px phone ───────────────────────────────────────────────────────────

test.describe('on a 375 px phone', () => {
  test.use({viewport: {width: 375, height: 812}});

  test('the Kunder list has no sideways scroll and names stay whole', async ({page}) => {
    await login(page);
    await page.evaluate(() => showView('customers'));
    const beta = page.locator('#customers-content .cust-card', {hasText: 'Browser Beta'});
    await expect(beta).toBeVisible();
    expect(await overflow(page)).toBe(0);
    // A name squeezed to a letter per line is many times taller than a line.
    const name = beta.locator('.cust-card-name-text');
    expect((await name.boundingBox()).height).toBeLessThan(40);
    const score = beta.locator('.cust-card-metrics > span').first();
    expect((await score.boundingBox()).height).toBeLessThan(30);
  });

  for (const view of ['hosts', 'browser', 'docs']) {
    test(`${view} has no sideways scroll`, async ({page}) => {
      await login(page);
      await page.evaluate(v => showView(v), view);
      await expect(page.locator('#view-' + view)).toHaveClass(/\bactive\b/);
      await page.waitForTimeout(500);
      expect(await overflow(page)).toBe(0);
    });
  }

  test('Administrasjon has no sideways scroll', async ({page}) => {
    await login(page);
    await page.evaluate(() => openAdmin('integrations'));
    await expect(page.locator('#view-admin')).toHaveClass(/\bactive\b/);
    await page.waitForTimeout(500);
    expect(await overflow(page)).toBe(0);
  });

  test('the alert channel labels read as words', async ({page}) => {
    await login(page);
    await page.evaluate(() => openAdmin('alerts'));
    const label = page.locator('label', {has: page.locator('#alert-notify-teams')});
    expect((await label.boundingBox()).height).toBeLessThan(40);
  });

  test('the Docs text takes the width of the screen', async ({page}) => {
    await login(page);
    await page.evaluate(() => showView('docs'));
    await expect(page.locator('#docs-repo-content h1').first()).toBeVisible();
    expect((await page.locator('#docs-repo-content').boundingBox()).width).toBeGreaterThan(300);
  });
});
