// One user, two tabs: Browser Alpha in the first, Browser Beta in the second.
// The server kept one "active customer" per user, shared by every tab, so the
// tab opened last decided where the other tab's note was saved, whose runs
// its Audit tab listed and whose files and network it showed. Every call a
// customer page makes names its customer now; this drives both tabs in turns
// and checks that each only ever shows, reads and writes its own.
const { test, expect } = require('@playwright/test');
const { inApp, expectSignedIn } = require('./app.cjs');

const PASSWORD = 'Browser-test123!';
const ALPHA = 'Browser_Alpha';
const BETA = 'Browser_Beta';

async function login(page) {
  await page.goto('/');
  await page.locator('#login-username').fill('browser-tabs');
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

// Every API call a page makes: the path with its query, and the body.
function recordCalls(page) {
  const calls = [];
  page.on('request', req => {
    const url = new URL(req.url());
    if (!url.pathname.startsWith('/api/')) return;
    calls.push(url.pathname + url.search + ' ' + (req.postData() || ''));
  });
  return calls;
}

async function openTab(page, tab) {
  await page.locator('#cust-tab-' + tab).click();
  await expect(page.locator('#cust-panel-' + tab)).toBeVisible();
}

test('two tabs of one user each keep their own customer', async ({browser}) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
  });
  const a = await context.newPage();
  const b = await context.newPage();
  const callsA = recordCalls(a);
  const callsB = recordCalls(b);

  // Both tabs signed in to the same account; Beta opened last.
  await login(a);
  await a.goto('/#/customer/' + ALPHA + '/detaljer');
  await expect(a.locator('#view-customer-detail .cust-title')).toHaveText('Browser Alpha');
  await b.goto('/#/customer/' + BETA + '/detaljer');
  await expect(b.locator('#view-customer-detail .cust-title')).toHaveText('Browser Beta');

  // Detaljer: each tab's connection card and files are its own customer's.
  await expect(a.locator('#files-creds')).toContainText('Browser Alpha');
  await expect(b.locator('#files-creds')).toContainText('Browser Beta');
  await expect(b.locator('#files-rawdata')).toContainText('30. september 2026');
  await expect(a.locator('#files-rawdata')).not.toContainText('30. september 2026');

  // Notes, saved in turns. The tab opened first saves after the other tab
  // opened its customer: the save that used to land on Beta.
  const noteA = 'alpha-note-' + Date.now();
  const noteB = 'beta-note-' + Date.now();
  await a.locator('#detail-notes-textarea').fill(noteA);
  await b.locator('#detail-notes-textarea').fill(noteB);
  await a.locator('#detail-notes-save').click();
  await expect(a.locator('#detail-notes-status')).toContainText('Lagret');
  await b.locator('#detail-notes-save').click();
  await expect(b.locator('#detail-notes-status')).toContainText('Lagret');
  await a.locator('#detail-notes-save').click();
  await expect.poll(async () => (await (await a.request.get('/api/customer/' + ALPHA + '/notes')).json()).notes).toBe(noteA);
  expect((await (await a.request.get('/api/customer/' + BETA + '/notes')).json()).notes).toBe(noteB);

  // Audit: each tab lists its own customer's runs. Beta has one; Alpha none.
  await openTab(b, 'audit');
  await openTab(a, 'audit');
  await expect(b.locator('#history-content')).toContainText('30. september 2026');
  await expect(a.locator('#history-content')).toContainText(await inApp(a, app => app.t('msg_no_prev_runs')));
  await expect(a.locator('#history-content')).not.toContainText('30. september 2026');

  // Nettverk: each reads its own customer's inventory.
  const invA = a.waitForRequest(r => r.url().includes('/api/dashboard/network-inventory/'));
  await openTab(a, 'nettverk');
  const invB = b.waitForRequest(r => r.url().includes('/api/dashboard/network-inventory/'));
  await openTab(b, 'nettverk');
  expect((await invA).url()).toContain('/network-inventory/' + ALPHA);
  expect((await invB).url()).toContain('/network-inventory/' + BETA);

  // Back on Detaljer in the first tab: still Alpha's note, after all that.
  await openTab(a, 'detaljer');
  await expect(a.locator('#detail-notes-textarea')).toHaveValue(noteA);

  // Not one call from either tab named the other tab's customer, and neither
  // asked the server to make a customer "active".
  const named = (calls, id) => calls.filter(c => c.includes(id));
  expect(named(callsA, BETA)).toEqual([]);
  expect(named(callsB, ALPHA)).toEqual([]);
  expect(callsA.concat(callsB).filter(c => c.includes('/customers/switch'))).toEqual([]);
  // Each tab's current customer is its own page's.
  expect(await inApp(a, app => app.currentCustomerId())).toBe(ALPHA);
  expect(await inApp(b, app => app.currentCustomerId())).toBe(BETA);
  await context.close();
});
