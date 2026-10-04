// Stored data from devices, integrations and other technicians must reach the
// SPA as text. The CSP no longer runs inline event attributes, but one
// unescaped value is still markup in someone else's view: a forged control, a
// form, a link. Handler arguments travel in data attributes and must arrive
// exactly as stored.
const { test, expect } = require('@playwright/test');
const { inApp } = require('./app.cjs');

const XSS = '<img src=x onerror="window.__xss=1;window.opener&&(window.opener.__xss=1)">';
const BREAKOUT = "x');window.__xss=1;//";
// Hosts persist in the shared fixture database; keep each test's labels apart.
const unique = () => Math.random().toString(36).slice(2, 8) + ' ';

// The admin account: security.spec enrols browser-tech in MFA mid-run.
async function login(page) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect.poll(async () => (await page.request.get('/api/auth/me')).status()).toBe(200);
  await expect(page.locator('#login-password')).not.toBeVisible();
}

async function expectInert(page, root) {
  expect(await page.locator(root + ' img').count()).toBe(0);
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();
}

test('SSH host fields stay text in the Hosts view, the edit form and inline handlers', async ({page}) => {
  await login(page);
  const host = {
    label: 'Label ' + unique() + XSS, group_name: 'Group ' + XSS, notes: 'Notes </textarea>' + XSS,
    hostname: '192.0.2.10', username: 'admin', port: 22, device_type: 'linux', auth_method: 'password',
  };
  const created = await page.request.post('/api/ssh/hosts', {data: host});
  expect(created.ok(), await created.text()).toBeTruthy();
  const hostId = (await created.json()).host.id;
  // The server now refuses this username, but rows saved before that rule
  // still hold whatever was typed. Serve one, so the client is what is tested.
  host.username = BREAKOUT;
  await page.route(url => new URL(url).pathname === '/api/ssh/hosts', async route => {
    const response = await route.fetch();
    const body = await response.json();
    for (const h of body.hosts || []) if (h.id === hostId) h.username = BREAKOUT;
    await route.fulfill({response, json: body});
  });
  await page.route('**/api/ssh/hosts/' + hostId, async route => {
    const response = await route.fetch();
    const body = await response.json();
    if (body.host) body.host.username = BREAKOUT;
    await route.fulfill({response, json: body});
  });

  await inApp(page, app => app.showView('hosts'));
  const card = page.locator('#hosts-content .card', {hasText: host.label});
  await expect(card.locator('strong')).toHaveText(host.label);
  await expect(card).toContainText(host.group_name);
  await expectInert(page, '#hosts-content');

  // The RDP button carries hostname, username and id in data attributes, and
  // its handler hands them to the RDP view exactly as stored.
  const rdp = card.getByRole('button', {name: 'RDP'});
  expect(await rdp.getAttribute('data-hostname')).toBe(host.hostname);
  expect(await rdp.getAttribute('data-username')).toBe(host.username);
  expect(await rdp.getAttribute('data-host-id')).toBe(hostId);
  await expectInert(page, '#hosts-content');
  await rdp.click();
  await expect(page.locator('#view-rdp')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#rdp-user-input')).toHaveValue(host.username);
  await expect(page.locator('#rdp-host-input')).toHaveValue(hostId);
  await expect(page.locator('#view-rdp img')).toHaveCount(0);
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();

  await page.locator('[data-click-handler="showView"][data-view="hosts"]').first().evaluate(el => el.click());
  await page.locator('#hosts-content .card', {hasText: host.label}).locator('[data-click-handler="sshEditHost"]').click();
  await expect(page.locator('#ssh-e-label')).toHaveValue(host.label);
  await expect(page.locator('#ssh-e-group')).toHaveValue(host.group_name);
  await expect(page.locator('#ssh-e-user')).toHaveValue(host.username);
  await expect(page.locator('#ssh-e-notes')).toHaveValue(host.notes);
  await expectInert(page, '#hosts-content');
});

test('command output and errors from SSH devices are rendered as text', async ({page}) => {
  await login(page);
  const label = 'Exec ' + unique() + XSS;
  const created = await page.request.post('/api/ssh/hosts', {data: {
    label: label, hostname: '192.0.2.11', username: 'root', device_type: 'linux', auth_method: 'password',
  }});
  expect(created.ok(), await created.text()).toBeTruthy();
  await page.route('**/api/ssh/exec', route => route.fulfill({json: {results: [
    {host_label: label, exit_code: 0, stdout: '</pre>' + XSS, stderr: XSS, error: XSS},
  ]}}));

  // Opening the view loads the key list; let it settle before switching tab.
  await inApp(page, app => app.showView('ssh'));
  await expect(page.locator('#ssh-content .loader')).toHaveCount(0);
  await inApp(page, app => app.sshShowExec());
  await page.locator('#ssh-exec-hosts label', {hasText: label}).locator('input').check();
  await page.locator('#ssh-exec-cmd').fill('uname -a');
  await page.locator('#ssh-exec-cmd').press('Enter');
  await expect(page.locator('#ssh-exec-results pre').first()).toHaveText('</pre>' + XSS);
  await expect(page.locator('#ssh-exec-results strong')).toHaveText(label);
  await expectInert(page, '#ssh-content');
});

test('device data from FortiGate, Tailscale and UniFi APIs is rendered as text', async ({page}) => {
  await login(page);

  // FortiGate fleet cards, as last read (stored, from the firmware inventory).
  await page.route('**/api/fortigate/fleet', route => route.fulfill({json: {fortigates: [{
    customer_id: BREAKOUT, host: XSS, hostname: XSS, customer_name: XSS, model: XSS, firmware: XSS,
    firmware_status: 'eol', read_at: null, read_error: XSS, has_token: true,
  }]}}));
  await inApp(page, app => app.dashLoadFortiGates());
  await expect(page.locator('#dash-fg-content .card strong').last()).toHaveText(XSS);
  await expect(page.locator('#dash-fg-content .fg-card-foot')).toContainText(XSS);
  await expectInert(page, '#dash-fg-content');
  // And as read live.
  await page.route('**/api/fortigate/all', route => route.fulfill({json: {fortigates: [{
    customer_id: BREAKOUT, hostname: XSS, customer_name: XSS, model: XSS, firmware: XSS, serial: XSS,
    uptime: XSS, status: 'error', error: XSS, cpu_pct: 1, mem_pct: 2, vpn_tunnels: 0, policy_count: 4,
  }]}}));
  await inApp(page, app => app.fgPollAll());
  await expect(page.locator('#dash-fg-content .card .font-mono').last()).toHaveText(XSS);
  await expectInert(page, '#dash-fg-content');

  // A firewall's detail panel: threats, the rule audit and what the device
  // itself reports, fed the way the poller returns it.
  const under = prefix => url => new URL(url).pathname.startsWith(prefix);
  await page.route(under('/api/fortigate/threats/'), route => route.fulfill({json: {
    summary: {critical: 1, high: 0, medium: 0, low: 0, total: 1},
    recent: [{timestamp: XSS, type: XSS, severity: 'critical', srcip: XSS, attack: XSS}],
  }}));
  await page.route(under('/api/fortigate/firewall-audit/'), route => route.fulfill({json: {
    score: 50, total_rules: 1, enabled: 1, issues: [{name: XSS, issue: XSS, severity: 'critical', detail: XSS}],
  }}));
  await page.route(under('/api/dashboard/poll/'), route => route.fulfill({json: {devices: [{
    name: XSS, status: 'online', vendor: 'fortigate', model: XSS, firmware: XSS, cpu_pct: 5, mem_pct: 7, sessions: 3, vpn_tunnels: 1,
    extra: {
      interfaces: [{name: XSS, type: XSS, ip: '192.0.2.1', mask: XSS, link: true, speed: 1000}],
      vpn_tunnels: [{name: XSS, remote_gw: XSS, status: 'up'}],
      ssl_vpn_users: [{user: XSS, remote_ip: XSS, tunnel_ip: XSS, duration: 60}],
    },
  }]}}));
  await page.locator('#dash-fg-content [data-click-handler="dashFgDetail"]').first().evaluate(card => card.click());
  await expect(page.locator('.fg-detail-panel table').first()).toContainText(XSS);
  await expectInert(page, '#dash-fg-content');
  // The CIS check asks for the firewall's customer exactly as stored.
  await page.route(under('/api/fortigate/compliance/'), route => route.fulfill({json: {score: 50, findings: [{title: XSS, status: 'fail', detail: XSS}]}}));
  const [cis] = await Promise.all([
    page.waitForRequest(r => new URL(r.url()).pathname.startsWith('/api/fortigate/compliance/')),
    page.locator('.fg-detail-panel button[data-click-handler="fgComplianceCheck"]').evaluate(button => button.click()),
  ]);
  expect(new URL(cis.url()).pathname).toBe('/api/fortigate/compliance/' + encodeURIComponent(BREAKOUT));
  await expect(page.locator('.fg-detail-panel [id^="fg-compliance-"] table')).toContainText(XSS);
  await expectInert(page, '#dash-fg-content');

  // Tailscale device cards: OS and client version come from the device.
  await page.route('**/api/tailscale/devices', route => route.fulfill({json: {total: 1, online: 0, offline: 1, devices: [{
    id: BREAKOUT, hostname: XSS, os: XSS, client_version: XSS, tailscale_ip: XSS, user: XSS,
    last_seen_ago: XSS, online: false, tags: ['tag:' + XSS],
  }]}}));
  await inApp(page, app => app.tsLoadView());
  await expect(page.locator('#ts-content .card-clickable')).toContainText('OS: ' + XSS);
  await expectInert(page, '#ts-content');

  // UniFi Site Manager site table.
  await inApp(page, (app, xss) => {
    const host = document.createElement('div');
    host.id = 'unifi-fixture';
    host.innerHTML = app._renderSiteTable([
      {name: xss, status: 'online', model: xss, wan_ip: xss, sub_sites: [{name: xss, device_count: 1}, {name: xss}]},
      {name: xss, status: 'offline', wan_ip: xss, isp: xss, firmware: xss, model: xss},
    ]);
    document.body.appendChild(host);
  }, XSS);
  await expect(page.locator('#unifi-fixture strong').first()).toHaveText(XSS);
  await expectInert(page, '#unifi-fixture');
});

test('generated reports open in a sandboxed frame where none of their content runs', async ({page}) => {
  await login(page);
  const report = '<p id="marker">Quarterly report</p>' + XSS
    + '<script>window.__xss=1;window.opener&&(window.opener.__xss=1)</script>';
  await page.route('**/api/reports/batch-summary', route => route.fulfill({contentType: 'text/html', body: report}));
  await page.route('**/api/pentest/report', route => route.fulfill({contentType: 'text/html', body: report}));

  // A scan's findings are what the pentest report is made of: one scan,
  // answered here, and the report button on its result.
  await page.route('**/api/pentest/cms-scan', route => route.fulfill({json: {
    ok: true, cms: {}, findings: [{title: 'Finding', severity: 'low'}], summary: {},
  }}));
  const openers = {
    qbr: () => inApp(page, app => app.generateQBR()),
    pentest: async () => {
      await page.locator('[data-click-handler="showView"][data-view="pentest"]').first().evaluate(el => el.click());
      await page.locator('#pentest-target').fill('host.example.test');
      await page.locator('#view-pentest [data-click-handler="runCmsScan"]').click();
      await page.locator('#pentest-results [data-click-handler="_pentestReport"]').click();
    },
  };
  for (const name of Object.keys(openers)) {
    const [popup] = await Promise.all([page.waitForEvent('popup'), openers[name]()]);
    const frame = popup.locator('iframe');
    const sandbox = await frame.getAttribute('sandbox');
    expect(sandbox, name).not.toBeNull();
    expect(sandbox, name).not.toContain('allow-scripts');
    await expect(popup.frameLocator('iframe').locator('#marker'), name).toHaveText('Quarterly report');
    // Let the broken images fail so their onerror would have fired by now.
    await expect.poll(() => popup.evaluate(() =>
      [...document.querySelector('iframe').contentDocument.images].every(i => i.complete)), {message: name}).toBe(true);
    expect(await popup.evaluate(() => [window.__xss, document.querySelector('iframe').contentWindow.__xss]), name)
      .toEqual([undefined, undefined]);
    expect(await page.evaluate(() => window.__xss), name).toBeUndefined();
    await popup.close();
  }
});

// Serves one endpoint, matched on its path so query strings do not matter.
async function serve(page, pathname, body) {
  await page.route(url => new URL(url).pathname === pathname, route => route.fulfill({json: body}));
}

test('ALSO and Uniweb renewal data is rendered as text, numbers included', async ({page}) => {
  await login(page);
  await serve(page, '/api/also/renewals', {
    renewals: [{
      id: 7, customer_name: XSS, service_display: XSS, vendor: XSS, term: XSS, quantity: 3, unit_price: 10,
      monthly_cost: 30, contract_end: XSS, days_left: 12, account_state: XSS, notes: XSS, handled: false,
    }],
    total_mrr: 30, currency: XSS, all_cached: 1, expired: 0, urgent_30d: 1, soon_60d: 0, upcoming: 0, beyond: 0,
    priced_count: 1,
  });
  // Counts are numbers in the API, but nothing on the wire guarantees it.
  await serve(page, '/api/also/api-stats', {total_calls: XSS, last_1min: XSS, last_5min: XSS, avg_response_ms: XSS, errors: XSS});
  await serve(page, '/api/uniweb/alerts', {total: XSS, items: [
    {customer_name: XSS, type: XSS, item_name: XSS, expiry_date: XSS, days_remaining: 3},
  ]});
  await serve(page, '/api/uniweb/partner/orders', {
    total_outstanding: 100, overdue_total: 0, overdue_count: 0, open_count: XSS, aging: {}, invoices: [],
  });

  // Fornyelser is a tab of Verktøy › Lisenser og hosting, its first.
  await inApp(page, app => app.showView('billing'));
  await page.locator('#view-billing .tab[data-tab="dash-renewals"]').click();
  const row = page.locator('#dash-renewals-content table').first().locator('tbody tr').first();
  await expect(row.locator('td').nth(1)).toHaveText(XSS);
  // The contract end date is cut to ten characters, then escaped.
  await expect(row.locator('td').nth(8)).toHaveText(XSS.slice(0, 10));
  await expect(page.locator('#dash-renewals-content .card', {hasText: 'MRR'}).first()).toContainText('30 ' + XSS);
  await expect(page.locator('#dash-uniweb-renewals tbody td').first()).toHaveText(XSS);
  await expect(page.locator('#uniweb-ar-card .uwar-kpi')).toHaveCount(4);
  await expect(page.locator('#also-api-stats')).toContainText('API:');
  await expectInert(page, '#dash-renewals-content');

  await serve(page, '/api/also/license-optimization', {
    summary: {currency: XSS, total_waste: 50, over_licensed_count: 1, under_licensed_count: 0, optimal_count: 0},
    customers: [{
      customer_name: XSS, total_paid: 3, total_assigned: 1, total_monthly_waste: 50, has_audit_data: true,
      licenses: [{product: XSS, paid_qty: 3, assigned_qty: 1, excess: 2, status: XSS, unit_price: 25, monthly_waste: 50}],
    }],
  });
  await page.locator('#dash-renewals-content [data-click-handler="alsoShowLicenseOptimization"]').click();
  const licence = page.locator('#dash-renewals-content tbody tr').first();
  await expect(licence.locator('td').first()).toHaveText(XSS);
  await expect(licence.locator('td').nth(4)).toHaveText(XSS);
  await expect(page.locator('#dash-renewals-content .card').first()).toContainText('50 ' + XSS);
  await expectInert(page, '#dash-renewals-content');
});

test('TLS certificates and discovered endpoints are rendered as text', async ({page}) => {
  await login(page);
  // A certificate says whatever the remote server chose to put in it.
  const cert = {
    host: XSS, port: 443, subject: {commonName: XSS}, issuer: {organizationName: XSS}, not_after: XSS,
    days_remaining: 20, expiring_soon: true, protocol_version: XSS, cipher: XSS, key_bits: 256, san: [XSS],
    serial_number: XSS,
  };
  await serve(page, '/api/tls/check', cert);
  await serve(page, '/api/tls/auto-discover', {count: XSS, endpoints: [{host: XSS, port: 443, label: XSS, source: XSS}]});
  await serve(page, '/api/tls/scan', {
    total: 2, valid: 0, expired: 0, expiring_soon: 1, weak_tls: 0, scanned_at: XSS,
    results: [Object.assign({label: XSS}, cert), {host: XSS, port: 8443, label: XSS, error: XSS}],
  });

  await inApp(page, app => app.showView('tls'));
  await page.locator('#tls-host').fill('cert.example.test');
  await page.locator('#tls-content button[data-click-handler="tlsCheckSingle"]').click();
  await expect(page.locator('#tls-single-result strong').first()).toHaveText(XSS + ':443');
  await expect(page.locator('#tls-single-result')).toContainText('SAN: ' + XSS);
  await expectInert(page, '#tls-content');

  await page.locator('#tls-discover-btn').click();
  await expect(page.locator('#tls-discovered')).toContainText('1 ' + XSS);
  await expect(page.locator('#tls-discovered')).toContainText(XSS + ':443');
  await expectInert(page, '#tls-content');

  await page.locator('#tls-scan-btn').click();
  // Errors sort first.
  const rows = page.locator('#tls-batch-result tbody tr');
  await expect(rows).toHaveCount(2);
  await expect(rows.first().locator('td').nth(2)).toHaveText(XSS);
  await expect(rows.nth(1).locator('td').nth(1)).toContainText(XSS + ':443');
  await expect(page.locator('#tls-batch-result')).toContainText(XSS.slice(0, 19));
  await expectInert(page, '#tls-content');
});

test('stored certificate and firmware state stays text in Varsler and the TLS list', async ({page}) => {
  await login(page);
  // Subject, issuer and labels come from a remote server or a device; the
  // customer name and device name from whoever typed them.
  await serve(page, '/api/dashboard/alerts', {
    credential_expiry: [], renewals: [], total_alerts: 2, categories: {},
    certificates: [{
      host: XSS, port: 443, label: XSS, customer_id: XSS, customer_name: XSS, subject: XSS, issuer: XSS,
      not_after: XSS, days_remaining: 3, chain_problem: XSS, kind: 'expiring', category: XSS, checked_at: XSS, stale: true,
    }],
    firmware: [{
      customer_id: XSS, customer_name: XSS, vendor: XSS, device_key: XSS, device_name: XSS, model: XSS,
      version: XSS, latest: XSS, status: 'eol', category: XSS, checked_at: XSS, read_error: XSS,
    }],
    coverage: {tls: {endpoints: XSS, unreachable: XSS, last_checked: XSS}, firmware: {devices: XSS, unknown: XSS, last_read: XSS}},
  });
  // Other specs leave events and hosting alerts behind in the shared fixture;
  // only the two served items are under test here.
  await serve(page, '/api/activity-log', {entries: []});
  await serve(page, '/api/alerts/history', {entries: [], total: 0});
  await serve(page, '/api/uniweb/alerts', {total: 0, items: []});
  await inApp(page, app => app.openOverviewTab('dash-alerts'));
  await expect(page.locator('#dash-alerts .notif-row')).toHaveCount(2);
  await expect(page.locator('#dash-alerts .notif-row .cust').first()).toHaveText(XSS);
  await expectInert(page, '#dash-alerts');

  await serve(page, '/api/tls/certificates', {count: 1, endpoints: [{
    host: XSS, port: 443, label: XSS, customer_name: XSS, subject: XSS, issuer: XSS, not_after: XSS,
    days_remaining: 3, status: XSS, chain_valid: false, chain_problem: XSS, checked_at: XSS, error: XSS, stale: false,
  }]});
  await inApp(page, app => app.showView('tls'));
  const row = page.locator('#tls-known .tls-table tbody tr');
  await expect(row).toHaveCount(1);
  await expect(row.locator('td').nth(2)).toHaveText(XSS);
  // The remove button carries the host exactly as stored.
  expect(await row.locator('[data-click-handler="tlsForget"]').getAttribute('data-host')).toBe(XSS);
  await expectInert(page, '#tls-content');
});

test('the customer licence panel renders ALSO subscriptions as text', async ({page}) => {
  await login(page);
  // The row id and the click handler's argument both carry the subscription id.
  const accountId = 'sub"><img src=x onerror="window.__xss=1">';
  await page.route(url => new URL(url).pathname.startsWith('/api/also/subscriptions/'), route => route.fulfill({json: {
    subscriptions: [{
      ServiceDisplayName: XSS, VendorDisplayName: XSS, BillingStartDate: XSS, ContractEndDate: XSS,
      AccountState: XSS, AccountId: accountId, Quantity: 4,
    }],
  }}));
  await page.route(url => new URL(url).pathname.startsWith('/api/also/subscription/'), route => route.fulfill({json: {
    subscription: {ContractId: XSS, Fields: [{DisplayName: XSS, Value: XSS}]},
  }}));

  // Detaljer's Lisenser card holds them; the panel stands in for it here.
  await inApp(page, app => {
    const box = document.createElement('div'); box.id = 'cust-licenses-panel';
    document.body.appendChild(box);
    return app.loadCustomerLicenses('acct-1');
  });
  const row = page.locator('#cust-licenses-panel tbody tr').first();
  await expect(row.locator('td').first()).toHaveText(XSS);
  await expect(row.locator('td').nth(2)).toHaveText('4');
  await expect(row.locator('td').nth(4)).toHaveText(XSS.slice(0, 10));
  await expect(row.locator('td').nth(6)).toHaveText(XSS);
  await expectInert(page, '#cust-licenses-panel');

  // The click handler finds the detail row by the id exactly as stored.
  await row.click();
  const detail = page.locator('#cust-licenses-panel > div > table > tbody > tr').nth(1);
  await expect(detail).toBeVisible();
  expect(await detail.getAttribute('id')).toBe('also-sub-' + accountId);
  await expect(detail).toContainText(XSS);
  await expectInert(page, '#cust-licenses-panel');
});
