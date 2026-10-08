const {test, expect} = require('@playwright/test');
const { inApp, expectSignedIn } = require('./app.cjs');

async function login(page, language = 'en') {
  await page.addInitScript(language => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', language);
    localStorage.setItem('sybr-theme', 'dark');
  }, language);
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

for (const language of ['no', 'en']) {
  test(`IT Glue explains the missing Save button to a read-only administrator in ${language}`, async ({page}, testInfo) => {
    await page.setViewportSize({width:language === 'no' ? 390 : 1280,height:900});
    await page.route('**/api/auth/me', async route => {
      const response = await route.fetch();
      const body = await response.json();
      if (body.user) body.user.can_write = false;
      await route.fulfill({response, json:body});
    });
    await login(page, language);
    await inApp(page, app => app.openAdmin('integrations'));
    await page.locator('[data-config="itglue-config"]').click();
    const panel = page.locator('#itglue-config');
    await expect(panel).toBeVisible();
    await expect(panel.locator('[data-click-handler="saveITGlueSettings"]')).toBeHidden();
    const notice = panel.locator('.readonly-settings-notice');
    await expect(notice).toBeVisible();
    await expect(notice).toContainText(language === 'no' ? 'Lagreknappen er skjult' : 'The Save button is hidden');
    await expect(notice).toContainText(language === 'no' ? 'Administrasjon > Brukere' : 'Administration > Users');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await panel.screenshot({path:testInfo.outputPath(`itglue-readonly-${language}.png`)});
  });
}

test('a rejected provider token cannot log a valid Hub user out', async ({page}) => {
  await login(page);
  let refreshes = 0;
  let vendorCalls = 0;
  page.on('request', r => { if (r.url().endsWith('/api/auth/refresh')) refreshes++; });
  // Also protects against older endpoints accidentally forwarding vendor 401.
  await page.route('**/api/tailscale/test', route => {
    vendorCalls++;
    return route.fulfill({status:401,json:{error:'Vendor token rejected', error_type:'auth_error'}});
  });
  await inApp(page, app => {
    app.openAdmin('integrations');
    app.toggleIntegConfig('ts-config');
    document.querySelector('#input-ts-api-key').value = 'synthetic-token';
    return app.tsTestConnection();
  });
  await expect(page.locator('#ts-config-msg')).toContainText('Vendor token rejected');
  await expect(page.locator('#login-password')).not.toBeVisible();
  expect(refreshes).toBe(0);
  expect(vendorCalls).toBe(1);
  expect((await page.request.get('/api/auth/me')).status()).toBe(200);
});

test('CSS-hidden Autotask and myITprocess panels toggle and close each other', async ({page}) => {
  await login(page);
  await inApp(page, app => { app.openAdmin('integrations'); app.toggleIntegConfig('autotask-config'); });
  await expect(page.locator('#autotask-config')).toBeVisible();
  await inApp(page, app => app.toggleIntegConfig('myitprocess-config'));
  await expect(page.locator('#autotask-config')).not.toBeVisible();
  await expect(page.locator('#myitprocess-config')).toBeVisible();
  await inApp(page, app => app.toggleIntegConfig('myitprocess-config'));
  await expect(page.locator('#myitprocess-config')).not.toBeVisible();
});

test('concurrent expired access requests refresh once and recover', async ({page}) => {
  await login(page);
  const cookies = await page.context().cookies();
  await page.context().clearCookies();
  await page.context().addCookies(cookies.filter(c => c.name !== 'access_token'));
  let refreshes = 0;
  await page.route('**/api/auth/refresh', async route => {
    refreshes++;
    await new Promise(resolve => setTimeout(resolve, 100));
    await route.continue();
  });
  const result = await inApp(page, app => Promise.all([
    app.apiFetch('/api/auth/me'), app.apiFetch('/api/auth/me'), app.apiFetch('/api/auth/me')
  ]));
  expect(result.every(r => r && r.user)).toBe(true);
  expect(refreshes).toBe(1);
  await expect(page.locator('#login-password')).not.toBeVisible();
});

test('a temporary refresh failure keeps the current view', async ({page}) => {
  await login(page);
  await page.route('**/api/auth/me', route => route.fulfill({status:401,json:{error:'expired'}}));
  await page.route('**/api/auth/refresh', route => route.fulfill({status:503,json:{error:'unavailable'}}));
  await inApp(page, app => app.apiFetch('/api/auth/me'));
  await expect(page.locator('#login-password')).not.toBeVisible();
});

test('failed writes are not repeated and the error ID is visible in English', async ({page}) => {
  await login(page);
  let calls = 0;
  await page.route('**/api/synthetic-write', route => {
    calls++;
    expect(route.request().headers()['accept-language']).toBe('en');
    return route.fulfill({status:500, json:{error:'Norsk reserve', error_key:'err_internal_error',
      error_type:'internal_error', error_id:'abc123'}});
  });
  await inApp(page, app => app.apiFetch('/api/synthetic-write', {method:'POST'}));
  expect(calls).toBe(1);
  await expect(page.locator('.toast').last()).toContainText('Error ID: abc123');
  await expect(page.locator('.toast').last()).not.toContainText('Norsk');
  const retryId = await page.locator('.toast').last().getAttribute('data-retry-id');
  // The retry action is forgotten once used. The toast stays on screen for
  // its 300 ms exit, so a double click reaches Try Again twice: it must
  // retry once, not repeat the failed write.
  await page.locator('.toast').last().getByRole('button', {name:'Try Again'}).dblclick();
  await expect.poll(() => calls).toBe(2);
  await expect(page.locator(`.toast[data-retry-id="${retryId}"]`)).toHaveCount(0);
  await page.waitForTimeout(300);
  expect(calls).toBe(2);
});

// The hosting card on the customer page's Detaljer tab, answered by the spec.
async function openHostingCard(page, body) {
  await page.route('**/api/uniweb/customer/Browser_Alpha', route => route.fulfill({json: body}));
  await page.evaluate(() => { location.hash = '#/customer/Browser_Alpha/detaljer'; });
  const card = page.locator('#customer-uniweb-panel');
  await expect(card.locator('.card')).toBeVisible();
  return card;
}

test('parallel provider failures give one toast and clear DNS loading states', async ({page}) => {
  await login(page);
  // Both lookups are held until both have been asked for, so they fail
  // together: two rows opened at once must give one toast, not two.
  let calls = 0;
  let release;
  const bothAsked = new Promise(resolve => { release = resolve; });
  await page.route('**/api/uniweb/dns/*', async route => {
    if (++calls === 2) release();
    await bothAsked;
    await route.fulfill({status:502,json:{error:'Unavailable',error_type:'integration_error',
      error_key:'err_uniweb_auth'}});
  });
  const card = await openHostingCard(page, {matched:true, account_name:'Synthetic Account',
    domains:[{domain:'one.example'},{domain:'two.example'}]});
  const rows = card.locator('tr[data-click-handler="uwToggleDns"]');
  await expect(rows).toHaveCount(2);
  await rows.nth(0).click();
  await rows.nth(1).click();
  await expect.poll(() => calls).toBe(2);
  await expect(page.locator('[data-error-key="err_uniweb_auth"]')).toHaveCount(1);
  await expect(card.locator('.uw-dns-row')).toHaveCount(2);
  await expect(card.locator('.loader')).toHaveCount(0);
  await expect(card).not.toContainText('No DNS records');
});

for (const width of [1280, 390]) {
  test(`integration configuration fits ${width}px and progress is translated`, async ({page}, testInfo) => {
    await page.setViewportSize({width,height:900});
    await login(page);
    await page.route('**/api/uniweb/status', route => route.fulfill({json:{configured:true,running:true,
      accounts_synced:2,total_accounts:10,current_account:'Synthetic Company With A Long Name',
      domains_found:5,sync_start_time:new Date(Date.now()-15000).toISOString()}}));
    await page.route('**/api/uniweb/accounts', route => route.fulfill({json:{total:1,accounts:[{
      id:'synthetic', name:'Synthetic Account', customer_name:'Synthetic Customer',domain_count:3,
      subscription_count:2,monthly_total:100,earliest_renewal:'2027-01-01'}]}}));
    await page.route('**/api/uniweb/sync', route => route.fulfill({json:{ok:true}}));
    // Credentials stored, so the card checks its status, lists the accounts
    // and offers Synkroniser.
    await page.route('**/api/settings', async route => {
      if (route.request().method() !== 'GET') return route.continue();
      const response = await route.fetch();
      const body = await response.json();
      body.uniweb_password_set = true;
      await route.fulfill({response, json:body});
    });
    await inApp(page, app => app.openAdmin('integrations'));
    await page.locator('[data-config="also-config"]').click();
    await page.locator('[data-config="uniweb-config"]').click();
    await expect(page.locator('#uniweb-accounts-container')).toContainText('Synthetic Account');
    await page.locator('#uniweb-sync-btn').click();
    await expect(page.locator('#also-config')).not.toBeVisible();
    await expect(page.locator('#uniweb-config')).toBeVisible();
    await expect(page.locator('#uniweb-config-msg')).toContainText('2 of 10 accounts');
    await expect(page.locator('#uniweb-config-msg')).toContainText('Elapsed:');
    expect(await page.locator('.uniweb-sync-row').first().evaluate(el => getComputedStyle(el).display)).toBe('flex');
    expect(await page.locator('.uniweb-progress-track').evaluate(el => el.getBoundingClientRect().height)).toBe(8);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('#uniweb-config').screenshot({path:testInfo.outputPath(`integrations-${width}.png`)});
    // A running sync is polled every two seconds; the next poll speaks Norwegian.
    await inApp(page, app => app.setLanguage('no'));
    await expect(page.locator('#uniweb-config-msg')).toContainText('Forløpt tid:');
    await expect(page.locator('#uniweb-config-msg')).toContainText('Gjenstående:');
    await expect(page.locator('#uniweb-config-msg')).toContainText('2 av 10 kontoer');
    await page.locator('[data-config="uniweb-config"]').click();
    await expect(page.locator('#uniweb-config')).not.toBeVisible();
  });
}

test('hosting card reads current vendor field names and English headings', async ({page}) => {
  await login(page);
  const box = await openHostingCard(page, {matched:true,
    account_name:'Synthetic Account',subscriptions:[{Service:'Test Hosting',Username:'example.test',
      'Price per month':'NOK 100','Renewed until':'2027-01-01'}],
    domains:[{domain:'example.test'}],email:[{'':'mail@example.test',Type:'Mailbox'}]});
  await expect(box).toContainText('Test Hosting');
  await expect(box).toContainText('mail@example.test');
  await expect(box).toContainText('Domains');
  await expect(box).toContainText('Subscriptions');
  await expect(box).toContainText('Email accounts');
  await expect(box).not.toContainText('Abonnementer');
});

test('late integration settings preserve typed text, passwords and checkbox edits', async ({page}) => {
  await login(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let settingsRequests = 0;
  await page.route('**/api/settings', async route => {
    settingsRequests++;
    await gate;
    await route.fulfill({json:{smtp_server:'old.example.invalid',smtp_user:'saved@example.invalid',smtp_port:465,
      smtp_password:'old-secret',email_auto_send:false,email_default_recipient:'saved-recipient@example.invalid'}});
  });
  await inApp(page, app => { app.openAdmin('integrations'); app.toggleIntegConfig('email-config'); });
  await expect.poll(() => settingsRequests).toBeGreaterThan(0);
  await page.locator('#input-smtp-server').fill('new.example.invalid');
  await page.locator('#input-smtp-password').fill('new-synthetic-password');
  await page.locator('#input-email-auto-send').check();
  release();
  await expect(page.locator('#input-smtp-user')).toHaveValue('saved@example.invalid');
  await expect(page.locator('#input-smtp-port')).toHaveValue('465');
  await expect(page.locator('#input-smtp-server')).toHaveValue('new.example.invalid');
  await expect(page.locator('#input-smtp-password')).toHaveValue('new-synthetic-password');
  await expect(page.locator('#input-email-auto-send')).toBeChecked();
  // A second status refresh must also preserve the draft.
  await inApp(page, app => app.loadIntegrationStatus());
  await expect(page.locator('#input-smtp-password')).toHaveValue('new-synthetic-password');
});

test('each document carries its own audit selection identity without requiring HTTPS randomUUID', async ({page,context}) => {
  await page.addInitScript(() => { Object.defineProperty(crypto,'randomUUID',{value:undefined}); });
  await login(page);
  const first = await inApp(page, app => app.auditTabHeaders().get('X-Audit-Tab'));
  expect(first).toMatch(/^[a-zA-Z0-9_-]{16,64}$/);
  const secondPage = await context.newPage();
  await secondPage.goto('/');
  await expectSignedIn(secondPage);
  const second = await inApp(secondPage, app => app.auditTabHeaders().get('X-Audit-Tab'));
  expect(second).not.toBe(first);
  let transmitted;
  await page.route('**/api/auth/me', async route => {
    transmitted = route.request().headers()['x-audit-tab'];
    await route.continue();
  });
  await inApp(page, app => app.apiFetch('/api/auth/me'));
  expect(transmitted).toBe(first);
  await secondPage.close();
});

test('integration cards distinguish stored, verified, failed and stale checks', async ({page}) => {
  let state = 'configured';
  await login(page, 'en');
  const saved = await (await page.request.get('/api/settings')).json();
  await page.route('**/api/settings', route => route.fulfill({json:{...saved,
    itglue_api_key:'••••••', integration_health:{...saved.integration_health,
      itglue:{state, checked_at:state === 'configured' ? null : '2026-10-01T12:00:00+00:00'}
    }
  }}));
  await inApp(page, app => app.openAdmin('integrations'));
  const label = page.locator('#itglue-integ-label');
  for (const [value, text] of [['configured','Saved · unverified'],['verified','Connection verified'],['failed','Connection check failed'],['stale','Check is older than 24 hours']]) {
    state = value;
    await inApp(page, app => app.loadIntegrationStatus());
    await expect(label).toContainText(text);
    if (value !== 'configured') await expect(label).toContainText('Last checked');
  }
  await page.reload();
  await expectSignedIn(page);
  await inApp(page, app => app.openAdmin('integrations'));
  await expect(label).toContainText('Check is older than 24 hours');
});

test.afterEach(async ({page}) => {
  await page.unrouteAll({behavior:'wait'});
});
