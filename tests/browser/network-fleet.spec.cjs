// Verktøy › Nettverk opens on what the hub last read from the firewalls, not
// on a live poll of every one of them. It used to call /api/fortigate/all on
// open (each customer's FortiGate signed in to, ten seconds each at worst),
// and "Oppdater nå" read the list, polled each customer again and read the
// list a third time. The firewalls are answered by the spec.
const { test, expect } = require('@playwright/test');
const { expectSignedIn, inApp } = require('./app.cjs');

const HOURS_AGO = h => new Date(Date.now() - h * 3600 * 1000).toISOString();
const STORED = {fortigates: [
  {customer_id: 'Browser_Alpha', customer_name: 'Browser Alpha', host: '192.0.2.10', hostname: 'FW-ALPHA', model: 'FortiGate-60F',
    firmware: 'v7.4.8', firmware_status: 'current', read_at: HOURS_AGO(3), checked_at: HOURS_AGO(3), read_error: '', has_token: true},
  {customer_id: 'Browser_Beta', customer_name: 'Browser Beta', host: '192.0.2.20', hostname: '', model: '',
    firmware: '', firmware_status: '', read_at: null, checked_at: null, read_error: '', has_token: false},
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
  // The dot is the last read, not "online now", and the card says so.
  await expect(alpha.locator('.fg-card-foot')).toHaveText('Siste lesing OK, 3 timer siden');
  await expect(alpha.locator('.dot')).toHaveAttribute('title', 'Siste lesing OK, 3 timer siden');
  // Never read: its address, and that it has not been read.
  await expect(beta).toContainText('192.0.2.20');
  await expect(beta.locator('.fg-card-foot')).toHaveText('Ikke lest ennå · mangler API-token');
  await expect(content).toContainText('Viser det huben sist leste fra brannmurene');
  await expect(content).toContainText('En grønn prikk betyr at siste lesing gikk bra, ikke at brannmuren svarer nå');
  await expect(content.locator('.kpi-card')).toHaveText([/2\s*Brannmurer/, /0\s*Firmware å følge opp/, /1\s*Ikke lest/, /3 timer siden\s*Sist lest/]);
  // Opening the tab reached no firewall.
  expect(asked).toEqual(['/api/fortigate/fleet']);

  await page.locator('#net-fortigates [data-click-handler="fgPollAll"]').click();
  await expect(alpha).toContainText('CPU: 7%');
  await expect(alpha).toContainText('FGT60F0000000001');
  // Read live, the dot does mean it answered.
  await expect(alpha.locator('.dot')).toHaveAttribute('title', 'Svarte nå');
  await expect(page.locator('#fg-live-status')).toContainText('Sist oppdatert');
  await expect(content).not.toContainText('Viser det huben sist leste');
  // One live read: no second listing, no poll per customer.
  expect(asked).toEqual(['/api/fortigate/fleet', '/api/fortigate/all']);
});

// TODO D20. A firewall set up with its token said "Ikke lest ennå" until
// somebody pressed "Oppdater nå" or the daily firmware job ran. One that
// nobody has tried to read is read once, after the stored list is drawn.
const NEW = {fortigates: [
  {customer_id: 'Browser_Alpha', customer_name: 'Browser Alpha', host: '192.0.2.10', hostname: '', model: '',
    firmware: '', firmware_status: '', read_at: null, checked_at: null, read_error: '', has_token: true},
]};
const NEW_READ = () => ({read: 1, fortigates: [
  {customer_id: 'Browser_Alpha', customer_name: 'Browser Alpha', host: '192.0.2.10', hostname: 'FW-ALPHA', model: 'FortiGate-60F',
    firmware: 'v7.4.8', firmware_status: 'current', read_at: HOURS_AGO(0), checked_at: HOURS_AGO(0), read_error: '', has_token: true},
]});

// The first read, answered when the spec says so.
async function holdFirstRead(page) {
  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/fortigate/fleet/first-read', async route => {
    await held;
    await route.fulfill({json: NEW_READ()});
  });
  return () => release();
}

function recordAsked(page) {
  const asked = [];
  page.on('request', r => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith('/api/fortigate/') || path.startsWith('/api/dashboard/poll/')) asked.push(r.method() + ' ' + path);
  });
  return asked;
}

test('a firewall nobody has read is read once on opening, and says so meanwhile', async ({page}) => {
  const asked = recordAsked(page);
  await page.route('**/api/fortigate/fleet', route => route.fulfill({json: NEW}));
  const release = await holdFirstRead(page);
  await login(page);
  await page.evaluate(() => { location.hash = '#/network'; });

  const alpha = page.locator('#dash-fg-content .device-card', {hasText: 'Browser Alpha'});
  await expect(alpha.locator('.fg-card-foot')).toHaveText('Leses for første gang…');
  release();
  await expect(alpha.locator('.fg-card-foot')).toHaveText('Siste lesing OK, akkurat nå');
  await expect(alpha).toContainText('FW-ALPHA');
  await expect(page.locator('#dash-fg-content .kpi-card')).toContainText([/1\s*Brannmurer/, /0\s*Firmware å følge opp/, /0\s*Ikke lest/]);
  expect(asked).toEqual(['GET /api/fortigate/fleet', 'POST /api/fortigate/fleet/first-read']);
});

test('Oppdater nå while the first read is under way is not drawn over', async ({page}) => {
  await page.route('**/api/fortigate/fleet', route => route.fulfill({json: NEW}));
  await page.route('**/api/fortigate/all', route => route.fulfill({json: LIVE}));
  const release = await holdFirstRead(page);
  await login(page);
  await page.evaluate(() => { location.hash = '#/network'; });
  const content = page.locator('#dash-fg-content');
  await expect(content).toContainText('Leses for første gang…');

  await page.locator('#net-fortigates [data-click-handler="fgPollAll"]').click();
  await expect(content).toContainText('CPU: 7%');
  const answered = page.waitForResponse('**/api/fortigate/fleet/first-read');
  release();
  await answered;
  // Whatever the page does with the answer, it has done once it settles.
  await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 100)));
  await expect(content).toContainText('CPU: 7%');
  await expect(content).not.toContainText('Viser det huben sist leste');
});

test('a read-only account reads nothing on opening, and is told when it will be read', async ({page}) => {
  const asked = recordAsked(page);
  await page.route('**/api/auth/me', async route => {
    const response = await route.fetch();
    const me = await response.json();
    // Before signing in it is a 401 with no account in it.
    if (me.user) me.user.can_write = false;
    return route.fulfill({response, json: me});
  });
  await page.route('**/api/fortigate/fleet', route => route.fulfill({json: NEW}));
  await login(page);
  await page.evaluate(() => { location.hash = '#/network'; });

  const alpha = page.locator('#dash-fg-content .device-card', {hasText: 'Browser Alpha'});
  await expect(alpha.locator('.fg-card-foot')).toHaveText('Ikke lest ennå: leses ved neste firmware-sjekk');
  await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 100)));
  expect(asked).toEqual(['GET /api/fortigate/fleet']);
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

// Integrasjoner's FortiGate card said "Konfigurert" for one firewall or
// fifty, read or not. It counts them, and says "lest OK" beside its dot.
async function withFortiGateCounts(page, counts) {
  await page.route('**/api/settings', async route => {
    if (route.request().method() !== 'GET') return route.continue();
    const response = await route.fetch();
    return route.fulfill({response, json: Object.assign(await response.json(), {fortigate_fleet: counts})});
  });
}

test('the FortiGate integration card counts the firewalls and how their last read went', async ({page}) => {
  const read = new Date(Date.now() - 3600 * 1000).toISOString();
  await withFortiGateCounts(page, {state: 'failed', configured: 3, read_ok: 1, failed: 1, unread: 1, stale: 0, last_read: read});
  await login(page);
  await inApp(page, app => app.openAdmin('integrations'));
  const label = page.locator('#fg-integ-label');
  await expect(label).toHaveText(new RegExp('^1 av 3 lest OK · 1 feilet · 1 ikke lest ennå · Sist lest: '));
  const red = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--red').trim());
  expect(await page.locator('#fg-integ-dot').evaluate(el => el.style.background)).toBe('var(--red)');
  expect(red).not.toBe('');
  await page.unrouteAll({behavior: 'ignoreErrors'});
});

test('the FortiGate integration card is grey and says so with no firewall set up', async ({page}) => {
  await withFortiGateCounts(page, {state: 'off', configured: 0, read_ok: 0, failed: 0, unread: 0, stale: 0, last_read: null});
  await login(page);
  await inApp(page, app => app.openAdmin('integrations'));
  await expect(page.locator('#fg-integ-label')).toHaveText('Ikke konfigurert');
  await page.unrouteAll({behavior: 'ignoreErrors'});
});
