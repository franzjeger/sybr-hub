// The Tailscale card on a customer's Tilgang tab. Opening it asked the server
// twice, once for the customer's nodes and once for the whole tailnet to fill
// the assign list, and each answer was a fresh read of the tailnet. It now
// asks once, and the assign list comes in the same answer (TODO E30). An
// administrator can give the customer a tag of its own; nobody else sees the
// control. Tailscale itself is answered by the spec.
const { test, expect } = require('@playwright/test');
const { expectSignedIn } = require('./app.cjs');

const NODES = {
  configured: true,
  customer_id: 'Browser_Beta',
  tag: 'tag:customer-browser-beta',
  default_tag: 'tag:customer-browser-beta',
  tag_override: null,
  nodes: [{
    id: 'n-beta', name: 'beta-fw', hostname: 'beta-fw', os: 'linux', online: true,
    last_seen: null, last_seen_ago: null, tags: ['tag:customer-browser-beta'], source: 'tag',
    key_days_left: null, key_expiry_disabled: false,
    ip: '100.64.0.10', addresses: ['100.64.0.10'], dns_name: 'beta-fw.tailnet.example',
  }],
  unassigned: [{id: 'n-spare', name: 'spare-box', ip: '100.64.0.20'}],
};

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

// The tailnet calls the page makes, and the card's answer.
async function tailnet(page, nodes) {
  const asked = [];
  page.on('request', r => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith('/api/tailscale/')) asked.push(r.method() + ' ' + path);
  });
  await page.route('**/api/tailscale/customer/Browser_Beta/nodes', route => route.fulfill({json: nodes()}));
  return asked;
}

test('the Tailscale card asks once, assign list included', async ({page}) => {
  const asked = await tailnet(page, () => NODES);
  await login(page);
  await page.goto('/#/customer/Browser_Beta/tilgang');

  const card = page.locator('#customer-tailscale-panel');
  await expect(card.locator('.cust-ts-name')).toHaveText('beta-fw');
  await expect(card.locator('#cust-ts-device option')).toHaveText(['Knytt en node til kunden', 'spare-box (100.64.0.20)']);
  await expect(card).toContainText('Noder med taggen tag:customer-browser-beta i Tailscale');
  expect(asked).toEqual(['GET /api/tailscale/customer/Browser_Beta/nodes']);
});

test('an administrator gives the customer its own tag, and an empty field takes it back', async ({page}) => {
  let override = null;
  const sent = [];
  await tailnet(page, () => ({...NODES, tag: override || NODES.default_tag, tag_override: override}));
  await page.route('**/api/tailscale/customer/Browser_Beta/tag', async route => {
    const body = route.request().postDataJSON();
    sent.push(body);
    override = body.tag;
    await route.fulfill({json: {ok: true, customer_id: 'Browser_Beta', tag: override || NODES.default_tag,
      default_tag: NODES.default_tag, tag_override: override}});
  });
  await login(page);
  await page.goto('/#/customer/Browser_Beta/tilgang');

  const card = page.locator('#customer-tailscale-panel');
  const own = card.locator('details.cust-ts-tag');
  await expect(own).toBeVisible();
  await own.locator('summary').click();
  await expect(own).toContainText('Tomt felt gir tag:customer-browser-beta.');
  await expect(own.locator('#cust-ts-tag')).toHaveAttribute('placeholder', 'tag:customer-browser-beta');
  await own.locator('#cust-ts-tag').fill('tag:beta-oslo');
  await own.getByRole('button', {name: 'Lagre'}).click();
  await expect(card).toContainText('Noder med taggen tag:beta-oslo i Tailscale');
  await expect(card.locator('#cust-ts-tag')).toHaveValue('tag:beta-oslo');

  await card.locator('details.cust-ts-tag summary').click();
  await card.locator('#cust-ts-tag').fill('   ');
  await card.locator('details.cust-ts-tag').getByRole('button', {name: 'Lagre'}).click();
  await expect(card).toContainText('Noder med taggen tag:customer-browser-beta i Tailscale');
  expect(sent).toEqual([{tag: 'tag:beta-oslo'}, {tag: null}]);
});

test('a technician does not see the tag control', async ({page}) => {
  await tailnet(page, () => NODES);
  await page.route('**/api/auth/me', async route => {
    const response = await route.fetch();
    const body = await response.json();
    (body.user || body).role = 'technician';
    await route.fulfill({response, json: body});
  });
  await login(page);
  await page.goto('/#/customer/Browser_Beta/tilgang');

  const card = page.locator('#customer-tailscale-panel');
  await expect(card.locator('.cust-ts-name')).toHaveText('beta-fw');
  await expect(card.locator('details.cust-ts-tag')).toBeHidden();
  await expect(card.locator('#cust-ts-device')).toBeVisible();
});
