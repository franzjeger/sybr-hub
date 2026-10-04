const {test, expect} = require('@playwright/test');
const { inApp, expectSignedIn, expectStrings } = require('./app.cjs');

const PASSWORD = 'Browser-test123!';

// Norwegian interface, and nothing about the onboarding tour pre-set: these
// tests are about when it appears.
async function freshBrowser(page) {
  await page.addInitScript(() => {
    localStorage.setItem('ui_lang', 'no');
    localStorage.setItem('sybr-theme', 'dark');
  });
}

async function signIn(page, username) {
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

// _postAuthInit, which opens the tour, runs in the same tick that sets
// _currentUser, so once it is set the tour would already be showing.
async function signedInAgain(page) {
  await expect.poll(() => inApp(page, app => !!app._currentUser)).toBe(true);
}

// ── Onboarding tour ─────────────────────────────────────────────────────────

test('the onboarding tour does not cover the login screen', async ({page}) => {
  await freshBrowser(page);
  await page.goto('/');
  await expect(page.locator('#login-username')).toBeVisible();
  // The old tour was built while the scripts loaded; once the translations
  // are in, every script has run and it would be on screen by now.
  await expectStrings(page);
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);
});

test('the tour appears once after the first sign-in and not after a reload', async ({page}) => {
  await freshBrowser(page);
  await page.goto('/');
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);
  await signIn(page, 'browser-tech');

  const modal = page.getByRole('dialog', {name: 'Legg til en kunde'});
  await expect(modal).toBeVisible();
  await expect(modal).toContainText('Gå til Kunder og velg Ny kunde.');
  await expect(modal).not.toContainText('Hjem');

  const next = page.locator('#ob-next');
  await next.click();
  await expect(page.locator('#ob-title')).toHaveText('Gi tilgang til Microsoft 365');
  await next.click();
  await expect(page.locator('#ob-title')).toHaveText('Kjør en audit');
  await expect(page.locator('#ob-text')).toContainText('kunden');
  await next.click();
  await expect(page.locator('#ob-title')).toHaveText('Følg opp funnene');
  await expect(next).toHaveText('Fullfør');
  await next.click();
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);

  // No "do not show again" box to tick: finishing is enough.
  await page.reload();
  await signedInAgain(page);
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);
});

let adminCookies = null;

test('Escape dismisses the tour for good, and it is remembered per user', async ({page}) => {
  await freshBrowser(page);
  await page.goto('/');
  await signIn(page, 'browser-tech');
  await expect(page.locator('.onboarding-overlay')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);

  await page.reload();
  await signedInAgain(page);
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);

  // A colleague signing in on the same browser has not seen it yet.
  await inApp(page, app => app.doLogout());
  await expect(page.locator('#login-username')).toBeVisible();
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);
  await signIn(page, 'browser-admin');
  await expect(page.locator('.onboarding-overlay')).toBeVisible();
  await page.locator('#ob-skip').click();
  await expect(page.locator('.onboarding-overlay')).toHaveCount(0);
  // The signed-in tests below reuse this session instead of signing in again.
  adminCookies = await page.context().cookies();
});

// ── First run ───────────────────────────────────────────────────────────────

test('the first-run password hint states the rule the server enforces', async ({page}) => {
  await freshBrowser(page);
  await page.goto('/');
  await inApp(page, app => app.showLoginView('setup'));
  const field = page.locator('#setup-password');
  await expect(field).toHaveAttribute('placeholder', /10/);
  await expect(field).not.toHaveAttribute('placeholder', /8/);
  await expect(field).toHaveAttribute('title', /bokstav.*tall.*spesialtegn/);
});

// ── Signed in ───────────────────────────────────────────────────────────────
// One signed-in page, shared by these tests and moved between views rather
// than reloaded. Every signed-in load polls /api/vpn/status, which sits in the
// same 60-a-minute brute-force bucket as /api/auth/login, and the whole
// browser run shares one loopback address. The tour is marked done the way
// older versions did it, which must still keep it away.

test.describe('signed in as an administrator', () => {
  test.describe.configure({mode: 'serial'});
  let page;

  test.beforeAll(async ({browser}, testInfo) => {
    const context = await browser.newContext({baseURL: testInfo.project.use.baseURL});
    await context.addInitScript(() => {
      localStorage.setItem('onboarding_done', '1');
      localStorage.setItem('ui_lang', 'no');
      localStorage.setItem('sybr-theme', 'dark');
    });
    page = await context.newPage();
    if (adminCookies) {
      await context.addCookies(adminCookies);
    } else {
      const res = await page.request.post('/api/auth/login',
        {data: {username: 'browser-admin', password: PASSWORD, otp: ''}});
      expect(res.ok()).toBe(true);
    }
    await page.goto('/');
    await expectSignedIn(page);
  });

  test.afterAll(async () => {
    await page.context().close();
  });

  test('"Endre kanaler" opens the alert settings instead of a blank screen', async () => {
    await inApp(page, app => app.showView('overview'));
    await page.locator('#view-overview .tab', {hasText: 'Varsler'}).click();
    await page.getByRole('button', {name: 'Endre kanaler'}).click();

    await expect(page.locator('#view-admin')).toBeVisible();
    await expect(page.locator('#admin-pane-alerts')).toBeVisible();
    expect(await page.evaluate(() => location.hash)).toBe('#/admin/alerts');
    expect(await page.locator('.view.active').count()).toBe(1);
    await expect(page.locator('#alert-master-toggle')).toBeInViewport();
    await expect(page.locator('#alert-notify-teams')).toBeVisible();
  });

  test('a customer that was never audited is not reported as all clear', async () => {
    // The fixture has one audited customer (Browser Beta); every other one,
    // including those other specs add, has never been audited.
    await inApp(page, app => app.showView('overview'));
    await page.locator('#view-overview .tab', {hasText: 'Oppfølging'}).click();
    // Count from the list the page rendered, not a second request: specs
    // running alongside add customers, and a later request then counted ones
    // the page had not loaded yet, so the strip looked short by one.
    await expect.poll(() => inApp(page, app => !!(app._overviewData && app._overviewData.customers))).toBe(true);
    const never = await inApp(page, app => app._overviewData.customers.filter(c => !c.last_audit).length);
    expect(never).toBeGreaterThan(0);
    const attention = page.locator('.attn-strip .attn-title');
    await expect.poll(async () => Number(await attention.getAttribute('data-count'))).toBeGreaterThanOrEqual(never);
    const count = await attention.getAttribute('data-count');
    const green = await page.evaluate(() => {
      const probe = document.createElement('span');
      probe.style.color = 'var(--green)';
      document.body.appendChild(probe);
      const value = getComputedStyle(probe).color;
      probe.remove();
      return value;
    });
    expect(await attention.evaluate(el => getComputedStyle(el).color)).not.toBe(green);
    await expect(page.locator('.attn-strip')).toContainText(never + ' uten audit');
    // A never-audited customer's findings are unknown, not none.
    const row = page.locator('.customer-overview-table tbody tr', {hasText: 'Browser Alpha'});
    await expect(row.locator('.sev-count.sev-unknown')).toHaveText('Aldri auditert');
    await expect(row.locator('.sev-count.sev-none')).toHaveCount(0);

    await page.locator('.attn-action').click();
    await expect(page.locator('#overview-attention-badge')).toBeVisible();
    await expect(page.locator('.customer-overview-table tbody tr')).toHaveCount(Math.min(Number(count), 25));
    await page.locator('#overview-attention-badge').click();
    await expect(page.locator('#overview-attention-badge')).toHaveCount(0);
  });

  test('settings offer no in-app update and say where updates come from', async () => {
    await inApp(page, app => app.openAdmin('system'));
    await expect(page.locator('#settings-update-note')).toContainText('DEPLOYMENT.md');
    await expect(page.locator('#admin-pane-system').getByRole('button', {name: 'Oppdater nå'})).toHaveCount(0);
  });

  test('the Audit tab offers its reports from one button, and no server folder', async () => {
    await page.evaluate(() => { location.hash = '#/customer/Browser_Beta/audit'; });
    await expect(page.locator('#cust-panel-audit')).toBeVisible();
    // Beta's one run kept only its figures: the summary report is the
    // default, and the reports built from evidence are offered but off.
    const main = page.locator('#cust-report-main');
    await expect(main).toHaveText('Sammendragsrapport');
    await page.locator('#cust-report .split-caret').click();
    const menu = page.locator('#cust-report-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('button', {name: 'CSV-eksport'})).toBeDisabled();
    await expect(menu.getByRole('button', {name: 'Teknisk rapport (PDF)'})).toBeDisabled();
    await expect(menu.getByRole('button', {name: 'Last opp rapporter til IT Glue'})).toBeVisible();
    await expect(page.locator('#cust-panel-audit').getByRole('button', {name: 'Åpne mappe'})).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
  });

  test('integrations lead with what the product is for and drop placeholders', async () => {
    await inApp(page, app => app.openAdmin('integrations'));
    const grid = page.locator('#integ-active .integ-grid');
    await expect(grid).not.toContainText('Kommer snart');
    await expect(grid).not.toContainText('ConnectWise');
    await expect(grid).not.toContainText('Halo');

    const order = await grid.evaluate(el => Array.from(el.children, card => {
      const status = card.querySelector('[id$="-integ-status"]');
      return status ? status.id.replace(/-integ-status$/, '') : null;
    }));
    expect(order.slice(0, 4)).toEqual(['gdap', 'autotask', 'myitprocess', 'itglue']);
    expect(order).toEqual(['gdap', 'autotask', 'myitprocess', 'itglue', 'email', 'webhook',
      'fg', 'unifi-sm', 'ts', 'also', 'uniweb', 'claude']);
  });

  test('"Ikke konfigurert" looks the same on every card and gates what needs setup', async () => {
    await inApp(page, app => app.openAdmin('integrations'));
    // Wait until the cards have been painted from the server.
    await expect(page.locator('#itglue-integ-label')).toHaveText('Ikke konfigurert');
    await expect(page.locator('#claude-integ-label')).toHaveText('Ikke konfigurert');
    const looks = await page.evaluate(() => {
      const seen = new Set();
      document.querySelectorAll('#integ-active [id$="-integ-label"]').forEach(label => {
        if (label.textContent.trim() !== 'Ikke konfigurert') return;
        const dot = document.getElementById(label.id.replace(/-label$/, '-dot'));
        seen.add(getComputedStyle(label).color + ' / ' + getComputedStyle(dot).backgroundColor);
      });
      return Array.from(seen);
    });
    expect(looks).toHaveLength(1);

    const card = page.locator('#itglue-integ-status').locator('xpath=..');
    await expect(card.getByRole('button', {name: 'Importer kunder'})).toBeDisabled();
    await expect(card.getByRole('button', {name: 'Synkroniser dokumentasjon'})).toBeDisabled();
    await expect(page.locator('#itglue-needs-config')).toBeVisible();
  });

  test('scheduled tasks show their schedule in Norwegian', async () => {
    await inApp(page, app => app.openAdmin('alerts'));
    const table = page.locator('#task-scheduler-table');
    await expect(table).toContainText('Daglig 02:00');
    await expect(table).toContainText('Søndag 03:00');
    await expect(table).toContainText('Hver 6. time');
    await expect(table).not.toContainText('daily');
    await expect(table).not.toContainText('every');
    await expect(table).not.toContainText('sunday');
  });
});
