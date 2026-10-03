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

async function asBeta(page) {
  await page.evaluate(() => switchActiveCustomer('Browser_Beta'));
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
  await page.goto('/#/customer/Browser_Beta');
  const infra = page.locator('#customer-infra-panel');
  await expect(infra).not.toContainText('Infrastruktur-seksjonen');
  await infra.getByRole('button', {name: 'Åpne Verter'}).click();
  await expect(page.locator('#view-hosts')).toHaveClass(/\bactive\b/);
});

// ── Other views about the same customer ──────────────────────────────────────

test('Historikk lists the run the customer page reports, with a way to a report', async ({page}) => {
  await login(page);
  await asBeta(page);
  await page.evaluate(() => showView('history'));
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

test('the audit view and M365-status name the last run by date, and the button reads "Kjør audit" once', async ({page}) => {
  await login(page);
  await asBeta(page);
  await page.evaluate(() => showView('audit'));
  const idle = page.locator('#audit-idle');
  await expect(idle).toContainText('Siste audit: 30. september 2026 kl. 12:00');
  await expect(idle.locator('[data-click-handler="startAudit"]')).toHaveText(/^\s*Kjør audit\s*$/);
  await expect(idle.locator('[data-click-handler="startAudit"] svg')).toHaveCount(1);
  await page.evaluate(() => showView('home'));
  await expect(page.locator('#home-content')).toContainText('30. september 2026 kl. 12:00');
  await expect(page.locator('#home-content')).not.toContainText('2026-09-30_');
  // Beta is a GDAP customer: M365-status offers the audit the customer page offers.
  await expect(page.locator('#home-content')).not.toContainText('ikke M365-tilganger konfigurert');
});

test('the dashboard has no second scoreboard: the Helse tab is gone', async ({page}) => {
  await login(page);
  await page.evaluate(() => showView('overview'));
  await expect(page.locator('.dash-tab-btn[data-tab="dash-customers"]')).toBeVisible();
  await expect(page.locator('.dash-tab-btn[data-tab="dash-health"]')).toHaveCount(0);
});

test('Domener is part of the billing module', async ({page}) => {
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
  await expect(page.locator('.dash-tab-btn[data-tab="dash-domains"]')).toBeHidden();
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
  await expect(page.locator('#view-integrations')).toHaveClass(/\bactive\b/);
});

test('Policy-utrulling without the tenant grant says why, raises no toast, and is not offered in the menu', async ({page}) => {
  await login(page);
  await asBeta(page);
  // Hidden by the grant rule itself, not only by the closed menu around it.
  const entry = page.locator('.navdd-item[data-view="policy-deploy"]');
  expect(await entry.evaluate(el => getComputedStyle(el).display)).toBe('none');
  await recordToasts(page);
  const refused = [];
  page.on('response', r => { if (r.status() === 403) refused.push(r.url()); });
  await page.evaluate(() => showView('policy-deploy'));
  await expect(page.locator('#pd-no-grant')).toContainText('Kontoen din kan ikke endre kundens tenant');
  await page.locator('#pd-breakglass').fill('00000000-0000-0000-0000-000000000001');
  await expect(page.locator('#pd-plan-btn')).toBeDisabled();
  await page.waitForTimeout(500);
  expect(refused).toEqual([]);
  expect(await page.evaluate(() => window.__toasts)).toEqual([]);
});

// ── Nothing internal shown to a person ───────────────────────────────────────

test('the Wiki tab and its load errors are gone from Integrasjoner', async ({page}) => {
  await login(page);
  const missing = [];
  page.on('response', r => { if (r.url().includes('/api/docs/file') && r.status() === 404) missing.push(r.url()); });
  await page.evaluate(() => showView('integrations'));
  await expect(page.locator('#integ-active')).toBeVisible();
  await expect(page.locator('#integ-wiki')).toHaveCount(0);
  await expect(page.locator('#view-integrations')).not.toContainText('Kunne ikke laste dokumentasjon');
  expect(missing).toEqual([]);
});

test('a technician sees the changelog in Docs, not the API reference', async ({page}) => {
  await login(page, 'browser-tech');
  await page.evaluate(() => showView('docs'));
  await expect(page.locator('#docs-repo-content h1').first()).toHaveText('Endringslogg');
  await expect(page.locator('#view-docs .docs-tabs')).toBeHidden();
  await expect(page.locator('#view-docs')).not.toContainText(/ARCHITECTURE|TODO|CRITICAL REVIEW/);
});

test('Settings show the version, not the host, and paths only to an admin', async ({page}) => {
  await login(page);
  await page.evaluate(() => openSettings());
  await page.locator('.settings-tab-btn[data-tab="stab-advanced"]').click();
  const modal = page.locator('#settings-modal');
  await expect(page.locator('#settings-version-info')).toHaveText(/^Versjon: \d/);
  await expect(modal).not.toContainText(/Python:|Platform:|PID:|Branch:/);
  // The old product name is not a label or a placeholder any more.
  const placeholders = await modal.locator('input[placeholder]').evaluateAll(els => els.map(e => e.placeholder).join(' '));
  expect(placeholders).not.toContain('MSPToolkit');
  await page.locator('.settings-tab-btn[data-tab="stab-general"]').click();
  await expect(page.locator('#settings-current-dir')).toBeVisible();

  const tech = await page.context().browser().newPage();
  await login(tech, 'browser-tech');
  await tech.evaluate(() => openSettings());
  await expect(tech.locator('#input-audit-dir')).toBeHidden();
  await expect(tech.locator('.settings-tab-btn[data-tab="stab-backup"]')).toBeHidden();
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
  await page.evaluate(() => openSettings());
  await page.locator('.settings-tab-btn[data-tab="stab-users"]').click();
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
  for (const selector of ['.nav-btn', '#context-run-audit', '.dash-tab-btn']) {
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

  for (const view of ['hosts', 'browser', 'integrations', 'docs']) {
    test(`${view} has no sideways scroll`, async ({page}) => {
      await login(page);
      await page.evaluate(v => showView(v), view);
      await expect(page.locator('#view-' + view)).toHaveClass(/\bactive\b/);
      await page.waitForTimeout(500);
      expect(await overflow(page)).toBe(0);
    });
  }

  test('the alert channel labels read as words', async ({page}) => {
    await login(page);
    await page.evaluate(() => showView('integrations'));
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
