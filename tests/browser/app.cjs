// The interface is ES modules and keeps nothing on window, so a spec cannot
// call showView('vpn') or read _currentUser in the page as a global any more.
// inApp runs a function in the page with `app`: every export of every module,
// read live (app._currentUser is the value now, not when app was made).
//
// The modules are imported at the URL the page loaded them from. The shell
// gives main.js ?v=<digest> and the server writes the same ?v= into every
// import (app/web/routes/frontend.py); a module imported under any other URL
// would be a second copy with its own state, and calling it would change
// nothing on the page.
//
//   await inApp(page, app => app.showView('vpn'));
//   await inApp(page, (app, id) => app.overviewSelectCustomer(id), 'Browser_Alpha');
//   expect(await inApp(page, app => app.currentCustomerId())).toBe('Browser_Beta');
const fs = require('node:fs');
const path = require('node:path');
const { expect } = require('@playwright/test');

// main.js imports every module of the interface.
const MAIN = fs.readFileSync(path.join(__dirname, '..', '..', 'app', 'web', 'static', 'main.js'), 'utf8');
const MODULES = [...MAIN.matchAll(/^import\s[^'"]*['"]\.\/([\w-]+\.js)['"]/gm)].map(m => m[1]);

// Runs in the page: imports the modules at the page's own URLs and gathers
// their exports, as getters, into one object.
async function pageApp(modules) {
  const entry = document.querySelector('script[type="module"][src^="/static/main.js"]');
  if (!entry) throw new Error('the page has no main.js module');
  const version = new URL(entry.src, location.href).search;
  const app = {};
  for (const name of modules) {
    const module = await import('/static/' + name + version);
    for (const key of Object.keys(module)) {
      if (Object.prototype.hasOwnProperty.call(app, key)) throw new Error(key + ' is exported twice');
      Object.defineProperty(app, key, {get: () => module[key], enumerable: true});
    }
  }
  return app;
}

// fn(app, ...args) in the page. fn is sent as source and must use only its
// arguments; its result comes back as page.evaluate returns one.
async function inApp(page, fn, ...args) {
  const source = `(async () => (${fn.toString()})(await (${pageApp.toString()})(${JSON.stringify(MODULES)}), ...${JSON.stringify(args)}))()`;
  return page.evaluate(source);
}

// Signed in, and the strings loaded (t() answers a key with its text).
async function expectSignedIn(page) {
  await expect.poll(() => inApp(page, app => !!app._currentUser && app.t('btn_close') !== 'btn_close')).toBe(true);
}

// The strings loaded, signed in or not.
async function expectStrings(page) {
  await expect.poll(() => inApp(page, app => app.t('btn_close') !== 'btn_close')).toBe(true);
}

module.exports = { inApp, expectSignedIn, expectStrings, MODULES };
