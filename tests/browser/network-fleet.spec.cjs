// Verktøy › Nettverk opens on what the hub last read from the firewalls, not
// on a live poll of every one of them. It used to call /api/fortigate/all on
// open (each customer's FortiGate signed in to, ten seconds each at worst),
// and "Oppdater nå" read the list, polled each customer again and read the
// list a third time. The firewalls are answered by the spec.
const { test, expect } = require('@playwright/test');
const { expectSignedIn } = require('./app.cjs');

const STORED = {fortigates: [
  {customer_id: 'Browser_Alpha', customer_name: 'Browser Alpha', host: '192.0.2.10', hostname: 'FW-ALPHA', model: 'FortiGate-60F',
    firmware: 'v7.4.8', firmware_status: 'current', read_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(), read_error: '', has_token: true},
  {customer_id: 'Browser_Beta', customer_name: 'Browser Beta', host: '192.0.2.20', hostname: '', model: '',
    firmware: '', firmware_status: '', read_at: null, read_error: '', has_token: false},
]};
const LIVE = {fortigates: [
  {customer_id: 'Browser_Alpha', customer_name: 'Browser Alpha', host: '192.0.2.10', hostname: 'FW-ALPHA', model: 'FortiGate-60F',
    serial: 'FGT60F0000000001', firmware: 'v7.4.8', uptime: '12d', cpu_pct: 7, mem_pct: 41, vpn_tunnels: 2, policy_count: 33, status: 'online'},
]};

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

test('the FortiGate tab opens on the stored readings, and Oppdater nå reads every firewall once', async ({page}) => {
  const asked = [];
  page.on('request', r => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith('/api/fortigate/') || path.startsWith('/api/dashboard/poll/')) asked.push(path);
  });
  await page.route('**/api/fortigate/fleet', route => route.fulfill({json: STORED}));
  await page.route('**/api/fortigate/all', route => route.fulfill({json: LIVE}));
  await login(page);
  await page.evaluate(() => { location.hash = '#/network'; });

  const content = page.locator('#dash-fg-content');
  const alpha = content.locator('.device-card', {hasText: 'Browser Alpha'});
  const beta = content.locator('.device-card', {hasText: 'Browser Beta'});
  await expect(alpha).toContainText('FW-ALPHA');
  await expect(alpha).toContainText('v7.4.8');
  await expect(alpha.locator('.badge')).toHaveText('Oppdatert');
  await expect(alpha.locator('.fg-card-foot')).toHaveText('Lest 3 timer siden');
  // Never read: its address, and that it has not been read.
  await expect(beta).toContainText('192.0.2.20');
  await expect(beta.locator('.fg-card-foot')).toHaveText('Ikke lest ennå · mangler API-token');
  await expect(content).toContainText('Viser det huben sist leste fra brannmurene');
  await expect(content.locator('.kpi-card')).toHaveText([/2\s*Brannmurer/, /0\s*Firmware å følge opp/, /1\s*Ikke lest/, /3 timer siden\s*Sist lest/]);
  // Opening the tab reached no firewall.
  expect(asked).toEqual(['/api/fortigate/fleet']);

  await page.locator('#net-fortigates [data-click-handler="fgPollAll"]').click();
  await expect(alpha).toContainText('CPU: 7%');
  await expect(alpha).toContainText('FGT60F0000000001');
  await expect(page.locator('#fg-live-status')).toContainText('Sist oppdatert');
  await expect(content).not.toContainText('Viser det huben sist leste');
  // One live read: no second listing, no poll per customer.
  expect(asked).toEqual(['/api/fortigate/fleet', '/api/fortigate/all']);
});
