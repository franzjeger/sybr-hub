// The service worker (app/web/static/sw.js) controls the interface: the
// shell from the network, the offline page when there is none, versioned
// /static/ assets from its cache, and /api/ never from it.
//
// No page.route() here: with request interception on, Playwright bypasses the
// service worker, and these tests would watch the network instead of it.
const { test, expect } = require('@playwright/test');
const { expectSignedIn } = require('./app.cjs');

const PASSWORD = 'Browser-test123!';

async function open(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
    // Page loads, not the about:blank frame the interface holds.
    if (window === top) sessionStorage.setItem('loads', String(Number(sessionStorage.getItem('loads') || 0) + 1));
  });
  await page.goto('/');
  await expect(page.locator('#login-username')).toBeVisible();
}

// The first worker installs and takes the page (clients.claim()).
async function controlled(page) {
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller), {timeout: 10000}).toBe(true);
}

async function login(page) {
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill(PASSWORD);
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

const cacheName = page => page.evaluate(async () => (await caches.keys()).find(k => k.startsWith('msptoolkit-')));
const cachedPaths = page => page.evaluate(async () => {
  const cache = await caches.open((await caches.keys()).find(k => k.startsWith('msptoolkit-')));
  return (await cache.keys()).map(r => { const u = new URL(r.url); return u.pathname + u.search; }).sort();
});
const entryModule = page => page.locator('script[type="module"]').getAttribute('src');

test('the worker controls the interface, after load and after reload', async ({page, baseURL}) => {
  await open(page);
  await controlled(page);
  const registration = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.getRegistration();
    return {scope: reg.scope, script: reg.active.scriptURL};
  });
  expect(registration.scope).toBe(baseURL + '/');
  expect(new URL(registration.script).pathname).toBe('/static/sw.js');
  // What a browser that ran an earlier build still holds: the same worker at
  // the default scope, /static/, controlling nothing.
  await page.evaluate(() => navigator.serviceWorker.register('/static/sw.js'));
  const scopes = () => page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).map(r => r.scope).sort());
  expect(await scopes()).toEqual([baseURL + '/', baseURL + '/static/']);
  await page.reload();
  expect(await page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  // The page drops it.
  await expect.poll(scopes).toEqual([baseURL + '/']);
});

test('the first worker taking the page is not offered as a new version', async ({page}) => {
  await open(page);
  await controlled(page);
  // controllerchange has fired by now; give a toast or a reload the chance to happen.
  await page.waitForTimeout(500);
  await expect(page.locator('.toast', {hasText: 'Ny versjon tilgjengelig'})).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem('loads'))).toBe('1');
});

test('a versioned module comes from the worker cache on the next load', async ({page, context}) => {
  await open(page);
  await controlled(page);
  const entry = await entryModule(page);
  expect(entry).toMatch(/^\/static\/main\.js\?v=[0-9a-f]{12}$/);
  const fromWorker = [];   // what the worker itself fetched from the network
  context.on('request', request => { if (request.serviceWorker()) fromWorker.push(new URL(request.url()).pathname + new URL(request.url()).search); });

  // Controlled now, but nothing in the cache yet: the worker fetches it and keeps it.
  await page.reload();
  expect(fromWorker).toContain(entry);
  expect(await cachedPaths(page)).toContain(entry);

  fromWorker.length = 0;
  const [response] = await Promise.all([
    page.waitForResponse(r => new URL(r.url()).pathname + new URL(r.url()).search === entry),
    page.reload(),
  ]);
  expect(response.fromServiceWorker()).toBe(true);
  expect(fromWorker).not.toContain(entry);
  await expect(page.locator('#login-username')).toBeVisible();
});

test('/api/ and the shell are never answered from the cache, and only immutable assets are kept', async ({page}) => {
  await open(page);
  await controlled(page);
  const name = await cacheName(page);
  // Plant what a careless worker would serve: an API answer and a stale shell.
  await page.evaluate(async n => {
    const cache = await caches.open(n);
    await cache.put('/api/version', new Response('{"version":"from-cache"}', {headers: {'Content-Type': 'application/json'}}));
    await cache.put('/', new Response('<!doctype html><title>stale</title><p id="stale-shell">stale</p>', {headers: {'Content-Type': 'text/html'}}));
  }, name);
  const version = await page.evaluate(() => fetch('/api/version').then(r => r.json()));
  expect(version.version).not.toBe('from-cache');
  await page.reload();
  await expect(page.locator('#login-username')).toBeVisible();
  await expect(page.locator('#stale-shell')).toHaveCount(0);
  await page.evaluate(async n => {
    const cache = await caches.open(n);
    await cache.delete('/api/version');
    await cache.delete('/');
  }, name);

  // Sign in and use the interface; nothing it asks /api/ for is answered by
  // the worker or kept by it.
  const apiAnswers = [];
  page.on('response', r => { if (new URL(r.url()).pathname.startsWith('/api/')) apiAnswers.push(r.fromServiceWorker()); });
  await login(page);
  await page.evaluate(() => { location.hash = '#/customers'; });
  await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
  await expect(page.locator('#customers-content .card-clickable').first()).toBeVisible();
  expect(apiAnswers.length).toBeGreaterThan(0);
  expect(apiAnswers.filter(Boolean)).toEqual([]);

  // A failed request and an asset under someone else's version are not kept.
  const answers = await page.evaluate(() => Promise.all([
    fetch('/static/no-such-module.js?v=000000000000').then(r => r.status),
    fetch('/static/app.css?v=not-its-digest').then(r => r.status),
  ]));
  expect(answers).toEqual([404, 200]);
  const kept = await cachedPaths(page);
  expect(kept.filter(p => !p.startsWith('/static/'))).toEqual([]);
  expect(kept).not.toContain('/static/no-such-module.js?v=000000000000');
  expect(kept).not.toContain('/static/app.css?v=not-its-digest');
  // Unversioned: only the offline page's own files, kept at install.
  expect(kept.filter(p => !p.includes('?v='))).toEqual(['/static/offline.css', '/static/offline.html', '/static/offline.js']);
});

test('with the network gone the offline page shows, and the app comes back with it', async ({page, context}) => {
  await open(page);
  await controlled(page);
  await page.reload();   // controlled, so the modules go through the worker into its cache
  const entry = await entryModule(page);

  await context.setOffline(true);
  await page.reload();
  await expect(page.locator('h1')).toHaveText('Du er offline');
  await expect(page.locator('#offline-retry')).toBeVisible();
  // Its stylesheet came from the cache too.
  expect(await page.locator('.card').evaluate(el => getComputedStyle(el).borderRadius)).not.toBe('0px');
  // A versioned module is still there; the API is not.
  const offline = await page.evaluate(async e => ({
    module: await fetch(e).then(r => r.ok, () => false),
    api: await fetch('/api/health').then(() => 'answered', () => 'failed'),
  }), entry);
  expect(offline).toEqual({module: true, api: 'failed'});

  // The offline page reloads when the network returns, into the app.
  await context.setOffline(false);
  await expect(page.locator('#login-username')).toBeVisible({timeout: 10000});
});
