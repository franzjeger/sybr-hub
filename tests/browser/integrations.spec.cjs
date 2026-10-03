const {test, expect} = require('@playwright/test');

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
  await expect.poll(() => page.evaluate(() => !!_currentUser && !!_i18n.en)).toBe(true);
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
  await page.evaluate(() => {
    openAdmin('integrations');
    toggleIntegConfig('ts-config');
    document.querySelector('#input-ts-api-key').value = 'synthetic-token';
    return tsTestConnection();
  });
  await expect(page.locator('#ts-config-msg')).toContainText('Vendor token rejected');
  await expect(page.locator('#login-password')).not.toBeVisible();
  expect(refreshes).toBe(0);
  expect(vendorCalls).toBe(1);
  expect((await page.request.get('/api/auth/me')).status()).toBe(200);
});

test('CSS-hidden Autotask and myITprocess panels toggle and close each other', async ({page}) => {
  await login(page);
  await page.evaluate(() => { openAdmin('integrations'); toggleIntegConfig('autotask-config'); });
  await expect(page.locator('#autotask-config')).toBeVisible();
  await page.evaluate(() => toggleIntegConfig('myitprocess-config'));
  await expect(page.locator('#autotask-config')).not.toBeVisible();
  await expect(page.locator('#myitprocess-config')).toBeVisible();
  await page.evaluate(() => toggleIntegConfig('myitprocess-config'));
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
  const result = await page.evaluate(() => Promise.all([
    apiFetch('/api/auth/me'), apiFetch('/api/auth/me'), apiFetch('/api/auth/me')
  ]));
  expect(result.every(r => r && r.user)).toBe(true);
  expect(refreshes).toBe(1);
  await expect(page.locator('#login-password')).not.toBeVisible();
});

test('a temporary refresh failure keeps the current view', async ({page}) => {
  await login(page);
  await page.route('**/api/auth/me', route => route.fulfill({status:401,json:{error:'expired'}}));
  await page.route('**/api/auth/refresh', route => route.fulfill({status:503,json:{error:'unavailable'}}));
  await page.evaluate(() => apiFetch('/api/auth/me'));
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
  await page.evaluate(() => apiFetch('/api/synthetic-write', {method:'POST'}));
  expect(calls).toBe(1);
  await expect(page.locator('.toast').last()).toContainText('Error ID: abc123');
  await expect(page.locator('.toast').last()).not.toContainText('Norsk');
  const retryId = await page.locator('.toast').last().getAttribute('data-retry-id');
  await page.locator('.toast').last().getByRole('button', {name:'Try Again'}).click();
  await expect.poll(() => calls).toBe(2);
  expect(await page.evaluate(id => Object.hasOwn(window._toastRetryFns, id), retryId)).toBe(false);
});

test('parallel provider failures give one toast and clear DNS loading states', async ({page}) => {
  await login(page);
  let calls = 0;
  await page.route('**/api/uniweb/dns/*', route => {
    calls++;
    return route.fulfill({status:502,json:{error:'Unavailable',error_type:'integration_error',
      error_key:'err_uniweb_auth'}});
  });
  await page.evaluate(async () => {
    const host = document.createElement('table');
    host.id = 'dns-test';
    host.innerHTML = '<tbody><tr><td>one.example</td></tr><tr><td>two.example</td></tr></tbody>';
    document.body.appendChild(host);
    await Promise.all(Array.from(host.rows).map((row, i) => uwToggleDns(row, i + '.example')));
  });
  expect(calls).toBe(2);
  await expect(page.locator('[data-error-key="err_uniweb_auth"]')).toHaveCount(1);
  await expect(page.locator('#dns-test .loader')).toHaveCount(0);
  await expect(page.locator('#dns-test')).not.toContainText('No DNS records');
});

for (const width of [1280, 390]) {
  test(`integration configuration fits ${width}px and progress is translated`, async ({page}, testInfo) => {
    await page.setViewportSize({width,height:900});
    await login(page);
    await page.route('**/api/uniweb/status', route => route.fulfill({json:{running:true,
      accounts_synced:2,total_accounts:10,current_account:'Synthetic Company With A Long Name',
      domains_found:5,sync_start_time:new Date(Date.now()-15000).toISOString()}}));
    await page.route('**/api/uniweb/accounts', route => route.fulfill({json:{total:1,accounts:[{
      id:'synthetic', name:'Synthetic Account', customer_name:'Synthetic Customer',domain_count:3,
      subscription_count:2,monthly_total:100,earliest_renewal:'2027-01-01'}]}}));
    await page.evaluate(async () => {
      openAdmin('integrations');
      toggleIntegConfig('also-config');
      toggleIntegConfig('uniweb-config');
      await Promise.all([uniwebLoadAccounts(),uniwebPollStatus()]);
    });
    await expect(page.locator('#also-config')).not.toBeVisible();
    await expect(page.locator('#uniweb-config')).toBeVisible();
    await expect(page.locator('#uniweb-config-msg')).toContainText('2 of 10 accounts');
    await expect(page.locator('#uniweb-config-msg')).toContainText('Elapsed:');
    expect(await page.locator('.uniweb-sync-row').first().evaluate(el => getComputedStyle(el).display)).toBe('flex');
    expect(await page.locator('.uniweb-progress-track').evaluate(el => el.getBoundingClientRect().height)).toBe(8);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('#uniweb-config').screenshot({path:testInfo.outputPath(`integrations-${width}.png`)});
    await page.evaluate(async () => { setLanguage('no'); await uniwebPollStatus(); });
    await expect(page.locator('#uniweb-config-msg')).toContainText('Forløpt tid:');
    await expect(page.locator('#uniweb-config-msg')).toContainText('Gjenstående:');
    await expect(page.locator('#uniweb-config-msg')).toContainText('2 av 10 kontoer');
    await page.evaluate(() => toggleIntegConfig('uniweb-config'));
    await expect(page.locator('#uniweb-config')).not.toBeVisible();
  });
}

test('hosting card reads current vendor field names and English headings', async ({page}) => {
  await login(page);
  await page.route('**/api/uniweb/customer/synthetic', route => route.fulfill({json:{matched:true,
    account_name:'Synthetic Account',subscriptions:[{Service:'Test Hosting',Username:'example.test',
      'Price per month':'NOK 100','Renewed until':'2027-01-01'}],
    domains:[{domain:'example.test'}],email:[{'':'mail@example.test',Type:'Mailbox'}]}}));
  await page.evaluate(async () => {
    const box = document.createElement('div'); box.id = 'customer-uniweb-panel';
    document.body.appendChild(box);
    await _unifiedLoadUniwebCard('synthetic');
  });
  const box = page.locator('#customer-uniweb-panel');
  await expect(box).toContainText('Test Hosting');
  await expect(box).toContainText('mail@example.test');
  await expect(box).toContainText('Domains');
  await expect(box).toContainText('Subscriptions');
  await expect(box).toContainText('Email accounts');
  await expect(box).not.toContainText('Abonnementer');
});
