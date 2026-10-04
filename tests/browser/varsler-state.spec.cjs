// Varsler reads stored state. The fixture (tests/browser/server.py) stores a
// certificate five days from expiry and an end-of-life access point the way a
// TLS check and a firmware read store them, and sets up no alert channel: the
// alert engine has sent nothing, so the page can only show them from state.
const { test, expect } = require('@playwright/test');
const { inApp, expectSignedIn } = require('./app.cjs');

const PASSWORD = 'Browser-test123!';

async function login(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

test('Varsler lists a stored expiring certificate and an end-of-life device with no alert channel', async ({page}) => {
  await login(page);
  await inApp(page, app => app.openOverviewTab('dash-alerts'));
  const alerts = page.locator('#dash-alerts');

  // Nothing was ever sent, and the sidebar says why.
  await expect(alerts.locator('.notif-side')).toContainText('Ingen kanal er satt opp');
  await expect(alerts.locator('.notif-group-label', {hasText: 'Sendt av automatiske varsler'})).toHaveCount(0);

  // The certificate: named by its endpoint and customer, under "now".
  const cert = alerts.locator('.notif-row', {hasText: 'shop.beta.example:443'});
  await expect(cert.locator('.notif-title')).toHaveText('TLS-sertifikat: shop.beta.example:443');
  await expect(cert.locator('.cust')).toHaveText('Browser Beta');
  await expect(cert).toContainText('KRITISK');
  await expect(cert).toContainText('Browser Beta nettbutikk');
  const now = alerts.locator('.notif-group-label', {hasText: 'Krever handling nå'});
  await expect(now).toBeVisible();

  // The device: end of life, named by device and customer.
  const device = alerts.locator('.notif-row', {hasText: 'Browser AP lager'});
  await expect(device.locator('.notif-title')).toHaveText('Enheten har nådd end-of-life: Browser AP lager');
  await expect(device.locator('.cust')).toHaveText('Browser Beta');
  await expect(device).toContainText('UniFi UAP-LR, 4.3.28');
  // End of life has nowhere to upgrade to; no arrow pointing at the same version.
  await expect(device).not.toContainText('→');

  // What the items rest on.
  await expect(alerts.locator('.notif-side')).toContainText('TLS-endepunkter sjekket: 1');
  await expect(alerts.locator('.notif-side')).toContainText('Enheter med lest firmware: 1');
  // The firmware tables are fresh, so nothing says otherwise.
  await expect(alerts.locator('.notif-side')).not.toContainText('Firmwaretabellen');

  // Each opens where it is handled: the certificate on Nettverk › TLS, with
  // the stored list showing it.
  await cert.getByRole('button', {name: 'Åpne TLS'}).click();
  await expect(page.locator('.net-sub-btn[data-tab="net-tls"]')).toHaveClass(/\bactive\b/);
  const known = page.locator('#tls-known .tls-table tbody tr', {hasText: 'shop.beta.example:443'});
  await expect(known).toBeVisible();
  await expect(known.locator('.tls-state')).toHaveText('Utløper snart');
  await expect(known).toContainText('Browser Beta');

  // The device on the customer's Nettverk tab.
  await inApp(page, app => app.openOverviewTab('dash-alerts'));
  await alerts.locator('.notif-row', {hasText: 'Browser AP lager'}).getByRole('button', {name: 'Åpne Nettverk'}).click();
  await expect(page.locator('#view-customer-detail')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#cust-tabs .tab[data-tab="nettverk"]')).toHaveAttribute('aria-selected', 'true');
});

test('Varsler names a firmware table past its window beside the unconfirmed count', async ({page}) => {
  // The fixture's tables are fresh. When to list a table is pinned with a
  // frozen clock in tests/test_varsler_reads_state.py; here the server's own
  // answer is given a stale UniFi table to see the page say so.
  await page.route('**/api/dashboard/alerts', async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.coverage.firmware.unknown = 3;
    body.coverage.firmware.stale_tables = [{vendor: 'unifi', as_of: '2026-03-30'}];
    await route.fulfill({response, json: body});
  });
  await login(page);
  await inApp(page, app => app.openOverviewTab('dash-alerts'));
  const side = page.locator('#dash-alerts .notif-side');
  await expect(side).toContainText('Firmware ikke bekreftet: 3.');
  await expect(side.locator('.notif-side-text.is-warn', {hasText: 'Firmwaretabellen for UniFi er utdatert'}))
    .toHaveText('Firmwaretabellen for UniFi er utdatert, siste oppdatering 2026-03-30. Enheter på nyeste kjente versjon kan derfor ikke bekreftes.');
});

test.describe('on a 375 px phone', () => {
  test.use({viewport: {width: 375, height: 812}});

  test('the stored certificate list scrolls inside its card, not the page', async ({page}) => {
    await login(page);
    await inApp(page, app => app.showNetworkTab('net-tls'));
    await expect(page.locator('#tls-known .tls-table tbody tr')).toHaveCount(1);
    const widths = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(widths[0]).toBeLessThanOrEqual(widths[1]);
  });
});
