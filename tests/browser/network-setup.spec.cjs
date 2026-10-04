// A customer's FortiGate and UniFi are set up on that customer's page, on its
// Nettverk tab. They used to be set up in Verktøy › Nettverk behind a "Kunde"
// field; that page is the every-customer fleet view now.
//
// Saving, listing and removing go to the real routes. What would reach a
// device (Test tilkobling, the quick check, a device's running config) is
// answered by the spec, the way the other network specs fake FortiGate and
// UniFi. The FortiGate the first test adds is on a loopback port nothing
// listens on: a fleet poll another spec makes while it exists fails at once
// instead of waiting out a timeout against an address that never answers.
const { test, expect } = require('@playwright/test');
const { expectSignedIn, inApp } = require('./app.cjs');

async function login(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

async function openNetworkTab(page) {
  await page.evaluate(() => { location.hash = '#/customer/Browser_Beta/nettverk'; });
  await expect(page.locator('#cust-panel-nettverk')).toBeVisible();
}

function posted(page, method, path) {
  return page.waitForRequest(r => r.method() === method && new URL(r.url()).pathname === path);
}

test('a FortiGate is added, listed, edited and removed on the customer\'s Nettverk tab', async ({page}) => {
  await login(page);
  try {
    await openNetworkTab(page);
    const setup = page.locator('#cust-net-setup');
    const add = setup.getByRole('button', {name: 'Legg til FortiGate'});
    await expect(add).toBeVisible();
    // The page is the customer's: no field asks which customer.
    await expect(page.locator('#cust-panel-nettverk [data-tool-customer]')).toHaveCount(0);

    // Add.
    await add.click();
    const form = setup.locator('form.cust-net-form');
    await expect(form.locator('.cust-net-form-title')).toHaveText('Legg til FortiGate');
    await form.getByLabel('Host (IP eller FQDN)').fill('127.0.0.1');
    await form.getByLabel('Port').fill('1');
    await form.getByLabel('API-token').fill('spec-token');

    // Test tilkobling, answered for the device.
    const tests = [];
    await page.route('**/api/fortigate/test', route => {
      tests.push(route.request().postDataJSON());
      return route.fulfill({json: {ok: true, hostname: 'FW-BETA', firmware: 'v7.4.4', serial: 'FGT60F0000000000'}});
    });
    await form.getByRole('button', {name: 'Test tilkobling'}).click();
    await expect(form.locator('.cust-net-result')).toHaveText('Tilkoblet: FW-BETA, firmware v7.4.4');
    expect(tests[0]).toMatchObject({host: '127.0.0.1', port: 1, api_token: 'spec-token'});

    // Lagre goes to the customer the form was opened for, and the list shows it.
    const save = posted(page, 'POST', '/api/fortigate/save/Browser_Beta');
    await form.getByRole('button', {name: 'Lagre'}).click();
    expect((await save).postDataJSON()).toMatchObject({host: '127.0.0.1', port: 1, api_token: 'spec-token', vdom: 'root'});
    const row = setup.locator('tr[data-net-row="fortigate"]');
    await expect(row).toContainText('127.0.0.1:1');
    await expect(row.locator('.badge')).toHaveText('Klar');
    await expect(form).toHaveCount(0);
    await expect(add).toHaveCount(0);

    // Edit. The stored token never comes back to the page: the field is
    // empty, and testing the saved device names the customer instead.
    await row.getByRole('button', {name: 'Endre'}).click();
    await expect(form.locator('.cust-net-form-title')).toHaveText('Endre FortiGate');
    await expect(form.getByLabel('Host (IP eller FQDN)')).toHaveValue('127.0.0.1');
    await expect(form.getByLabel('API-token')).toHaveValue('');
    await expect(form.getByLabel('API-token')).toHaveAttribute('placeholder', /Token lagret/);
    await form.getByRole('button', {name: 'Test tilkobling'}).click();
    await expect.poll(() => tests.length).toBe(2);
    expect(tests[1]).toMatchObject({host: '127.0.0.1', port: 1, customer_id: 'Browser_Beta'});
    expect(tests[1].api_token || '').toBe('');
    await form.getByLabel('VDOM').fill('kunde');
    const edit = posted(page, 'POST', '/api/fortigate/save/Browser_Beta');
    await form.getByRole('button', {name: 'Lagre'}).click();
    expect((await edit).postDataJSON()).not.toHaveProperty('api_token');
    await expect(row).toContainText('VDOM kunde');
    // Same address, no new token: the stored one was kept.
    await expect(row.locator('.badge')).toHaveText('Klar');

    // Remove, after saying what goes.
    await row.getByRole('button', {name: 'Fjern'}).click();
    await expect(page.locator('#confirm-modal-title')).toHaveText('Fjerne FortiGate 127.0.0.1 fra Browser Beta?');
    await expect(page.locator('#confirm-modal-body')).toContainText('API-tokenet slettes fra huben');
    const removal = posted(page, 'DELETE', '/api/fortigate/Browser_Beta');
    await page.locator('#confirm-modal-ok').click();
    await removal;
    await expect(row).toHaveCount(0);
    await expect(setup.getByRole('button', {name: 'Legg til FortiGate'})).toBeVisible();
    const listed = await (await page.request.get('/api/network-devices/Browser_Beta')).json();
    expect(listed.fortigate).toBeNull();
  } finally {
    // Whatever step failed, the fixture's customer is left without it.
    await page.request.delete('/api/fortigate/Browser_Beta');
  }
});

test('Verktøy › Nettverk is the fleet view and asks for no customer', async ({page}) => {
  await login(page);
  await page.evaluate(() => { location.hash = '#/network'; });
  await expect(page.locator('#view-network')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#view-network .net-sub-btn')).toHaveText(['FortiGate', 'UniFi', 'TLS']);
  await expect(page.locator('#view-network .net-sub-btn.active')).toHaveText('FortiGate');
  await expect(page.locator('#view-network [data-tool-customer]')).toHaveCount(0);
  await expect(page.locator('#net-devices, #net-audit')).toHaveCount(0);
});

// A listing with one of everything, and a quick check answer with the wide
// tables, all answered by the spec so nothing is stored for the customer.
const LISTING = {
  fortigate: {host: 'fw-hovedkontor-med-langt-navn.beta.example', port: 8443, vdom: 'root', verify_ssl: false, has_token: true, has_admin_password: false},
  unifi: {
    mode: 'direct', host: '', site: 'default', is_unifi_os: false, has_credentials: false,
    direct_devices: [
      {host: '192.0.2.31', device_type: 'ap', username: 'admin', has_password: true},
      {host: '192.0.2.32', device_type: 'switch', username: 'ubnt', has_password: false},
    ],
  },
};
const QUICK_CHECK = {
  fortigate: {
    hostname: 'FW-BETA', firmware: 'v7.4.4', policy_count: 41, admin_count: 2, vpn_tunnels: 3, interface_count: 12,
    ha_mode: 'standalone', serial: 'FGT60F0000000000', model: 'FortiGate-60F', uptime: '41d',
    admins: [{name: 'admin', profile: 'super_admin', trusthost: false, two_factor: false}],
    policy_warnings: ['Policy 7 tillater all trafikk fra wan til lan'],
  },
  unifi: {
    mode: 'direct', device_count: 1, reachable: 1, default_creds_count: 0, outdated_firmware_count: 0, eol_count: 0,
    devices: [{host: '192.0.2.31', ok: true, device_type: 'ap', model: 'U6-Pro', firmware: '6.6.77', hostname: 'ap-lager',
      mac: '02:00:00:00:00:31', ip: '192.0.2.31', http: true, ssh: true}],
  },
};

test('on a 375 px screen the tab, its UniFi form and the quick check fit without sideways scroll', async ({page}) => {
  await page.setViewportSize({width: 375, height: 812});
  await page.route('**/api/network-devices/Browser_Beta', route => route.fulfill({json: LISTING}));
  await page.route('**/api/network/quick-audit/Browser_Beta', route => route.fulfill({json: QUICK_CHECK}));
  const configs = [];
  await page.route('**/api/unifi/device-config', route => {
    configs.push(route.request().postDataJSON());
    return route.fulfill({json: {ok: true, config: 'system.cfg: users.1.name=admin'}});
  });
  await page.route('**/api/network/save-config-backup/Browser_Beta', route => route.fulfill({json: {ok: true}}));
  await login(page);
  await openNetworkTab(page);
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

  const setup = page.locator('#cust-net-setup');
  await expect(setup.locator('tr[data-net-row="fortigate"]')).toContainText('fw-hovedkontor-med-langt-navn.beta.example:8443');
  await expect(setup.locator('tr[data-net-row="unifi"]')).toContainText('2 enheter');
  expect(await overflow()).toBe(0);

  // The UniFi form, direct devices listed without their passwords.
  await setup.locator('tr[data-net-row="unifi"]').getByRole('button', {name: 'Endre'}).click();
  const devices = page.locator('#unifi-device-list tbody tr');
  await expect(devices).toHaveCount(2);
  await expect(devices.nth(0)).toContainText('passord lagret');
  await expect(devices.nth(1)).toContainText('felles UniFi-innlogging');
  expect(await overflow()).toBe(0);

  // The quick check's cards and tables.
  await page.locator('#btn-run-network-audit').click();
  const result = page.locator('#net-audit-result');
  await expect(result).toContainText('FortiGate · FW-BETA');
  await expect(result).toContainText('Advarsler (1)');
  await expect(result.locator('[data-unifi-card="192.0.2.31"]')).toContainText('ap-lager');
  expect(await overflow()).toBe(0);

  // A device's running config: the button names the customer, not a password.
  await result.locator('[data-unifi-card="192.0.2.31"]').getByRole('button', {name: 'Vis konfig'}).click();
  await expect(result.locator('[data-unifi-card="192.0.2.31"] pre')).toHaveText('system.cfg: users.1.name=admin');
  expect(configs).toEqual([{host: '192.0.2.31', customer_id: 'Browser_Beta'}]);
  expect(await overflow()).toBe(0);
});

// A new FortiGate from its factory settings, and the login the hub keeps for
// it, used to be set up in Administrasjon › Integrasjoner for whichever
// customer a Kunde field named. They are on the customer's Nettverk tab now;
// the firewall itself is answered by the spec.
test('a new FortiGate is set up from its factory settings on the Nettverk tab, and an admin downloads its login', async ({page}) => {
  let bootstrapped = false;
  await page.route('**/api/network-devices/Browser_Beta', route => route.fulfill({json: {
    fortigate: bootstrapped ? {host: '192.0.2.99', port: 8443, vdom: 'root', verify_ssl: true, has_token: true, has_admin_password: true} : null,
    unifi: null,
  }}));
  const sent = [];
  await page.route('**/api/fortigate/bootstrap', route => {
    sent.push(route.request().postDataJSON());
    bootstrapped = true;
    return route.fulfill({json: {ok: true, persisted: true, host: '192.0.2.99', admin_password: 'Spec-Admin-Pw-1', api_admin: 'msp_api_admin', api_token: 'spec-api-token'}});
  });
  await page.route('**/api/fortigate/credentials/Browser_Beta', route => route.fulfill({json: {
    ok: true, customer_name: 'Browser Beta', host: '192.0.2.99', port: 8443, admin_user: 'admin',
    admin_password: 'Spec-Admin-Pw-1', api_user: 'msp_api_admin', api_token: 'spec-api-token', bootstrapped_at: '2026-10-04T08:00:00+00:00',
  }}));
  await login(page);
  await openNetworkTab(page);
  const setup = page.locator('#cust-net-setup');

  await setup.getByRole('button', {name: 'Sett opp ny FortiGate'}).click();
  const form = setup.locator('form.cust-net-form');
  await expect(form.locator('.cust-net-form-title')).toHaveText('Sett opp ny FortiGate');
  await form.getByLabel('FortiGate IP').fill('192.0.2.99');
  await form.getByLabel('Hostname (valgfritt)').fill('FW-BETA');
  await form.getByRole('button', {name: 'Sett opp FortiGate'}).click();

  // For the customer whose page it is; no field asked which.
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toEqual({host: '192.0.2.99', hostname: 'FW-BETA', customer_id: 'Browser_Beta'});
  // The list shows the FortiGate it stored, and what it made stays to copy.
  await expect(setup.locator('tr[data-net-row="fortigate"]')).toContainText('192.0.2.99:8443');
  const answer = setup.locator('.cust-net-boot-answer');
  await expect(answer).toContainText('Spec-Admin-Pw-1');
  await expect(answer).toContainText('spec-api-token');
  await expect(answer).toContainText('En administrator kan laste ned påloggingsinformasjonen igjen');
  await expect(answer.getByRole('button', {name: 'Kopier token'})).toBeVisible();

  // An admin downloads the stored login from the row.
  const download = page.waitForEvent('download');
  await setup.locator('tr[data-net-row="fortigate"]').getByRole('button', {name: 'Last ned påloggingsinformasjon'}).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('fortigate-credentials-Browser_Beta.txt');
  const text = require('node:fs').readFileSync(await file.path(), 'utf8');
  expect(text).toContain('# Kunde:        Browser Beta');
  expect(text).not.toContain('# # ');
  expect(text).toContain('API token:      spec-api-token');
});

test('a factory setup that stopped after the password shows the password to keep', async ({page}) => {
  await page.route('**/api/network-devices/Browser_Beta', route => route.fulfill({json: {fortigate: null, unifi: null}}));
  await page.route('**/api/fortigate/bootstrap', route => route.fulfill({json: {
    ok: false, error: 'API-nøkkelen kunne ikke opprettes', steps: ['connect', 'password_set'],
    host: '192.0.2.99', admin_password: 'Spec-Kept-Pw-2', raw_output: 'execute api-user generate-key: denied',
  }}));
  await login(page);
  await openNetworkTab(page);
  const setup = page.locator('#cust-net-setup');
  await setup.getByRole('button', {name: 'Sett opp ny FortiGate'}).click();
  const form = setup.locator('form.cust-net-form');
  await form.getByLabel('FortiGate IP').fill('192.0.2.99');
  await form.getByLabel('FortiGate IP').press('Enter');
  await expect(form.locator('.cust-net-result')).toContainText('API-nøkkelen kunne ikke opprettes (connect → password_set)');
  const answer = form.locator('.cust-net-boot-answer');
  await expect(answer).toContainText('Delvis fullført');
  await expect(answer).toContainText('Spec-Kept-Pw-2');
  await expect(answer.locator('details pre')).toHaveText('execute api-user generate-key: denied');
});

test('Integrasjoner says where a customer\'s FortiGate is set up, and no setup asks which customer', async ({page}) => {
  await login(page);
  await inApp(page, app => app.openAdmin('integrations'));
  const card = page.locator('#admin-pane-integrations .integ-card', {has: page.locator('#fg-integ-status')});
  await expect(card).toContainText('Hver kundes FortiGate settes opp på kundens side, under Nettverk');
  await expect(card.locator('input, select, form')).toHaveCount(0);
  await card.getByRole('button', {name: 'Alle kunders nettverk'}).click();
  await expect(page.locator('#view-network')).toHaveClass(/\bactive\b/);
  // The only Kunde fields left: pentest's segmentation test and provisioning,
  // tools that are not on a customer's page.
  const tools = await page.locator('[data-tool-customer]').evaluateAll(els => els.map(el => el.dataset.toolCustomer).sort());
  expect(tools).toEqual(['pentest', 'provisioning']);
});
