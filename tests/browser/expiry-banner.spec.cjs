// A customer's credential expiry banner (Detaljer) and the badge on its
// Kunder card. Expired and critical were the same red tint, the same red
// title and the same red dot: only the title's words told a credential that
// had stopped working from one about to. Expired now has a solid red edge,
// a warning sign instead of a clock, and a solid badge on its line; every
// line says its state in words.
const { test, expect } = require('@playwright/test');
const { expectSignedIn, inApp } = require('./app.cjs');

const ALPHA = 'Browser_Alpha';
const item = (type, category, days) => ({
  customer_id: ALPHA, customer_name: 'Browser Alpha', type, category, days_remaining: days,
  expiry_date: new Date(Date.now() + days * 86400000).toISOString().slice(0, 10),
});
const EXPIRED = [item('secret', 'expired', -3), item('cert', 'critical', 4)];
const CRITICAL = [item('cert', 'critical', 4)];
const WARNING = [item('secret', 'warning', 20)];

async function login(page, theme) {
  await page.addInitScript(t => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
    localStorage.setItem('sybr-theme', t);
  }, theme);
  await page.route('**/api/expiry/check', route => route.fulfill({json: {items: EXPIRED, summary: {}}}));
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

// The banner as drawn: its edge, its icon, each line's badge, and the
// contrast of the title and the badges over what is behind them.
const look = banner => banner.evaluate(el => {
  function rgba(value) {
    const n = value.match(/[\d.]+/g).map(Number);
    if (value.startsWith('color(srgb')) for (let i = 0; i < 3; i++) n[i] *= 255;
    return n.length === 4 ? n : n.concat(1);
  }
  // The colour behind el: its own background and each ancestor's, laid over
  // one another down to the first opaque one.
  function behind(node) {
    const layers = [];
    for (let n = node; n; n = n.parentElement) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c[3] > 0) layers.push(c);
      if (c[3] === 1) break;
    }
    return layers.reverse().reduce((under, c) => under.map((v, i) => c[i] * c[3] + v * (1 - c[3])), [255, 255, 255]);
  }
  function lum(c) { return c.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }).reduce((a, v, i) => a + v * [.2126, .7152, .0722][i], 0); }
  function contrast(text, node) { const a = lum(rgba(getComputedStyle(text).color)), b = lum(behind(node)); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); }
  const title = el.querySelector('.expiry-banner-title');
  const badges = [...el.querySelectorAll('.expiry-item .cust-expiry-badge')];
  const lines = [...el.querySelectorAll('.expiry-item > span:last-child')];
  return {
    edge: getComputedStyle(el).borderLeftWidth,
    icon: title.querySelector('svg path').getAttribute('d').slice(0, 12),
    badges: badges.map(b => b.textContent),
    fills: badges.map(b => getComputedStyle(b).backgroundColor),
    inks: badges.map(b => getComputedStyle(b).color),
    contrast: [title, ...badges, ...lines].map(n => contrast(n, n)),
  };
});

for (const theme of ['dark', 'light']) {
  test(`an expired credential does not look like a critical one (${theme})`, async ({page}) => {
    await login(page, theme);
    await page.evaluate(id => { location.hash = '#/customer/' + id + '/detaljer'; }, ALPHA);
    const banner = page.locator('#expiry-banner-area .expiry-banner');
    await expect(banner).toHaveClass(/\bhas-expired\b/);
    await expect(banner.locator('.expiry-banner-title')).toHaveText('Legitimasjonen har utløpt!');
    const expired = await look(banner);
    expect(expired.badges).toEqual(['Utløpt', 'Kritisk']);
    // The expired line's badge is solid red under white; the critical
    // line's is a tint under red.
    expect(expired.fills[0]).not.toEqual(expired.fills[1]);
    expect(expired.inks[0]).toBe('rgb(255, 255, 255)');
    expect(expired.inks[1]).not.toBe('rgb(255, 255, 255)');

    await inApp(page, (app, items) => app.renderExpiryBanner({items}), CRITICAL);
    await expect(banner).toHaveClass(/\bhas-critical\b/);
    await expect(banner.locator('.expiry-banner-title')).toHaveText('Legitimasjonen utløper snart!');
    const critical = await look(banner);
    expect(critical.badges).toEqual(['Kritisk']);
    expect(expired.edge).toBe('4px');
    expect(critical.edge).toBe('1px');
    expect(expired.icon).not.toEqual(critical.icon);

    await inApp(page, (app, items) => app.renderExpiryBanner({items}), WARNING);
    await expect(banner).toHaveClass(/\bhas-warning\b/);
    const warning = await look(banner);
    expect(warning.badges).toEqual(['Utløper snart']);
    // The title, every badge and every line read at AA over the banner's tint.
    for (const ratio of [...expired.contrast, ...critical.contrast, ...warning.contrast]) expect(ratio).toBeGreaterThanOrEqual(4.5);
  });
}

// The badge on the Kunder card is the same one, and says the worst state.
test('the Kunder card badge is the banner\'s badge for the worst state', async ({page}) => {
  await login(page, 'dark');
  await page.evaluate(() => { location.hash = '#/customers'; });
  const card = page.locator('#view-customers .cust-expiry-badge').first();
  await expect(card).toHaveText('Utløpt');
  await expect(card).toHaveClass(/\bexpired\b/);
});
