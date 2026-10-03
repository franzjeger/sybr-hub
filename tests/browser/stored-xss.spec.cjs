// Stored data from devices, integrations and other technicians must reach the
// SPA as text. The CSP no longer runs inline event attributes, but one
// unescaped value is still markup in someone else's view: a forged control, a
// form, a link. Handler arguments travel in data attributes and must arrive
// exactly as stored.
const { test, expect } = require('@playwright/test');

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

  await page.evaluate(() => showView('hosts'));
  const card = page.locator('#hosts-content .card', {hasText: host.label});
  await expect(card.locator('strong')).toHaveText(host.label);
  await expect(card).toContainText(host.group_name);
  await expectInert(page, '#hosts-content');

  // The RDP button passes hostname, username and id through data attributes.
  await page.evaluate(() => { window.sshRdp = function() { window.__rdpArgs = Array.from(arguments); }; });
  await card.getByRole('button', {name: 'RDP'}).click();
  expect(await page.evaluate(() => window.__rdpArgs)).toEqual([host.hostname, host.username, hostId]);
  await expectInert(page, '#hosts-content');

  await page.evaluate(id => sshEditHost(id), hostId);
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
  await page.evaluate(() => showView('ssh'));
  await expect(page.locator('#ssh-content .loader')).toHaveCount(0);
  await page.evaluate(() => sshShowExec());
  await page.locator('#ssh-exec-hosts label', {hasText: label}).locator('input').check();
  await page.locator('#ssh-exec-cmd').fill('uname -a');
  await page.locator('#ssh-exec-cmd').press('Enter');
  await expect(page.locator('#ssh-exec-results pre').first()).toHaveText('</pre>' + XSS);
  await expect(page.locator('#ssh-exec-results strong')).toHaveText(label);
  await expectInert(page, '#ssh-content');
});

test('device data from FortiGate, Tailscale and UniFi APIs is rendered as text', async ({page}) => {
  await login(page);

  // Live FortiGate view, fed the way the live WebSocket feeds it.
  await page.evaluate(([xss, breakout]) => {
    window.fgComplianceCheck = function(id) { window.__cisArg = id; };
    liveRenderDevices([{
      name: xss, status: 'online', vendor: 'fortigate', model: xss, firmware: xss, wan_ip: xss, uptime: xss,
      cpu_pct: 5, mem_pct: 7, sessions: 3, vpn_tunnels: 1, ha_mode: xss, clients: 2, error: xss, customer_id: breakout,
      extra: {
        interfaces: [{name: xss, ip: '10.0.0.1', link: true, speed: 1000}],
        vpn_tunnels: [{name: xss, remote_gw: xss}],
        policies: [{id: 1, name: xss, src: xss, dst: xss, svc: xss, log: xss}],
        dhcp: [{interface: xss, range: xss}], dns: {primary: xss, secondary: xss},
        admins: [{name: xss, profile: xss}],
      },
    }]);
  }, [XSS, BREAKOUT]);
  await expect(page.locator('#dash-fg-content strong').first()).toContainText(XSS);
  await expectInert(page, '#dash-fg-content');
  await page.evaluate(() => liveShowDeviceDetail(0));
  await expect(page.locator('#dash-fg-content h3')).toContainText(XSS);
  await page.locator('#dash-fg-content button[data-click-handler="fgComplianceCheck"]').evaluate(button => button.click());
  expect(await page.evaluate(() => window.__cisArg)).toBe(BREAKOUT);
  await expectInert(page, '#dash-fg-content');

  // FortiGate fleet cards.
  await page.route('**/api/fortigate/all', route => route.fulfill({json: {fortigates: [{
    customer_id: BREAKOUT, hostname: XSS, customer_name: XSS, model: XSS, firmware: XSS, serial: XSS,
    uptime: XSS, status: 'online', cpu_pct: 1, mem_pct: 2, vpn_tunnels: 0, policy_count: 4,
  }]}}));
  await page.evaluate(() => dashLoadFortiGates());
  await expect(page.locator('#dash-fg-content .card strong').last()).toHaveText(XSS);
  await expectInert(page, '#dash-fg-content');

  // Tailscale device cards: OS and client version come from the device.
  await page.route('**/api/tailscale/devices', route => route.fulfill({json: {total: 1, online: 0, offline: 1, devices: [{
    id: BREAKOUT, hostname: XSS, os: XSS, client_version: XSS, tailscale_ip: XSS, user: XSS,
    last_seen_ago: XSS, online: false, tags: ['tag:' + XSS],
  }]}}));
  await page.evaluate(() => tsLoadView());
  await expect(page.locator('#ts-content .card-clickable')).toContainText('OS: ' + XSS);
  await expectInert(page, '#ts-content');

  // UniFi Site Manager site table.
  await page.evaluate(xss => {
    const host = document.createElement('div');
    host.id = 'unifi-fixture';
    host.innerHTML = _renderSiteTable([
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

  const openers = {
    qbr: () => generateQBR(),
    pentest: () => {
      window._lastPentestData = {findings: [{title: 'Finding'}], summary: {}};
      document.getElementById('pentest-target').value = 'host.example.test';
      return _pentestReport();
    },
  };
  for (const name of Object.keys(openers)) {
    const [popup] = await Promise.all([page.waitForEvent('popup'), page.evaluate(openers[name])]);
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
