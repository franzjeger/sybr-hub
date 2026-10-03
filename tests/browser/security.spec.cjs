const { test, expect } = require('@playwright/test');
const { createHmac } = require('node:crypto');

async function login(page, username) {
  await page.addInitScript(() => localStorage.setItem('onboarding_done', '1'));
  await page.goto('/');
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect.poll(async () => (await page.request.get('/api/auth/me')).status()).toBe(200);
}

test('login, header and footer branding images decode in the browser', async ({page}) => {
  await page.goto('/');
  const logos = page.locator('img[src^="/branding/"]');
  expect(await logos.count()).toBeGreaterThan(0);
  await expect.poll(() => logos.evaluateAll(images =>
    images.every(image => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0)
  )).toBe(true);
});

test('stored customer data stays data across two users and keyboard activation', async ({browser}) => {
  const attack = "Example');globalThis.auditExecuted=true;//";
  const technician = await browser.newContext();
  const techPage = await technician.newPage();
  await login(techPage, 'browser-tech');
  const created = await techPage.request.post('/api/customers/add-manual', {
    data: {name: attack}
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  await technician.close();

  const admin = await browser.newContext();
  const page = await admin.newPage();
  await login(page, 'browser-admin');
  // The actual renderer against the actual authenticated API: the Kunder
  // list prints the name and hands it to the archive button's handler,
  // which shows it in the typed confirmation.
  await page.evaluate(() => showView('customers'));
  const card = page.locator('#customers-content').getByText(attack, {exact: true});
  await expect(card).toBeVisible();
  const archive = page.locator(`#customers-content [data-click-handler="deleteCustomer"][data-name="${attack.replace(/"/g, '\\"')}"]`);
  await archive.focus();
  await expect(archive).toBeFocused();
  await archive.press('Enter');
  await expect(page.locator('#confirm-modal-body strong')).toHaveText(attack);
  expect(await page.evaluate(() => globalThis.auditExecuted)).toBeUndefined();
  await page.keyboard.press('Escape');
  await admin.close();
});

// Handler arguments travel in data-* attributes, escaped with esc(). Each
// payload must reach the registered handler exactly as written and run nothing.
test('handler arguments escaped into data attributes reach the handler intact', async ({page}) => {
  await login(page, 'browser-admin');
  const payloads = ["');globalThis.auditExecuted=true;//", "\\');globalThis.auditExecuted=true;//",
    '" autofocus onfocus="globalThis.auditExecuted=true', '&quot; onclick=&quot;globalThis.auditExecuted=true',
    // A raw newline was the danger inside an inline JavaScript string; in an
    // attribute it is just text. (CR LF becomes LF in any parsed attribute.)
    "x\ny\u2028z\tq", '<img src=x onerror=alert(1)>'];
  for (const value of payloads) {
    await page.evaluate(value => {
      const host = document.createElement('div'); host.id = 'escape-fixture';
      // The element the handler acts on, named by the hostile value itself.
      const target = document.createElement('p'); target.id = value; target.textContent = 'target';
      host.appendChild(target);
      host.insertAdjacentHTML('beforeend',
        '<button data-click-handler="hideElement" data-target="' + esc(value) + '">test</button>');
      document.body.appendChild(host);
    }, value);
    const button = page.locator('#escape-fixture button');
    expect(await button.evaluate(el => el.getAttributeNames())).toEqual(['data-click-handler', 'data-target']);
    await button.click();
    expect(await page.evaluate(value => document.getElementById(value).style.display, value)).toBe('none');
    expect(await page.evaluate(() => globalThis.auditExecuted)).toBeUndefined();
    await page.locator('#escape-fixture').evaluate(el => el.remove());
  }
});

test('logout rejects copied refresh and access tokens', async ({page}) => {
  await login(page, 'browser-admin');
  const cookies = await page.context().cookies();
  const oldAccess = cookies.find(c => c.name === 'access_token').value;
  const oldRefresh = cookies.find(c => c.name === 'refresh_token').value;
  expect((await page.request.post('/api/auth/logout')).ok()).toBeTruthy();
  await page.context().clearCookies();
  expect((await page.request.get('/api/auth/me', {headers:{Authorization:'Bearer '+oldAccess}})).status()).toBe(401);
  expect((await page.request.post('/api/auth/refresh', {data:{refresh_token:oldRefresh}})).status()).toBe(401);
});

test('MFA enrollment displays recovery once and subsequent login requires it', async ({page}) => {
  await login(page, 'browser-tech');
  await page.evaluate(() => showMfaSettings());
  const modal = page.locator('#confirm-modal');
  await modal.locator('input[type=password]').fill('Browser-test123!');
  await modal.locator('.btn-primary').click();
  await expect(modal.locator('pre')).toHaveText(/^[A-Z2-7]{32}$/);
  const secret = await modal.locator('pre').innerText();
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = [...secret].map(c => alphabet.indexOf(c).toString(2).padStart(5,'0')).join('');
  const key = Buffer.from(bits.match(/.{8}/g).map(byte => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const mac = createHmac('sha1', key).update(counter).digest();
  const otp = ((mac.readUInt32BE(mac[19] & 15) & 0x7fffffff) % 1000000).toString().padStart(6, '0');
  await modal.locator('input[type=text]').fill(otp);
  await modal.locator('.btn-primary').click();
  await expect(modal.locator('pre')).toContainText(/\n[0-9a-f]{32}/);
  const recovery = (await modal.locator('pre').innerText()).split('\n').slice(1);
  expect(recovery).toHaveLength(10);
  await modal.locator('#confirm-modal-body .btn-ghost').last().click();
  await expect(modal.locator('pre')).toHaveCount(0);
  expect((await page.request.post('/api/auth/logout')).status()).toBe(200);
  const credentials = {username:'browser-tech', password:'Browser-test123!'};
  expect((await page.request.post('/api/auth/login', {data:credentials})).status()).toBe(401);
  expect((await page.request.post('/api/auth/login', {data:{...credentials, otp:recovery[0]}})).status()).toBe(200);
  expect((await page.request.get('/api/auth/me')).status()).toBe(200);
});
