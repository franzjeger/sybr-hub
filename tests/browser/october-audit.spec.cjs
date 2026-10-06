const {test, expect} = require('@playwright/test');
const {inApp, expectSignedIn} = require('./app.cjs');

async function login(page, theme = 'dark') {
  await page.addInitScript(t => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'en');
    localStorage.setItem('sybr-theme', t);
  }, theme);
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expectSignedIn(page);
}

test('confirmation starts on Cancel, traps Tab, closes with Escape and restores focus', async ({page}) => {
  await login(page);
  const trigger = page.locator('#overview-export-toggle');
  await trigger.focus();
  await inApp(page, app => { app.showConfirm('Delete audit', 'Permanent deletion'); });
  await expect(page.locator('#confirm-modal-cancel')).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.locator('#confirm-modal-ok')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.locator('#confirm-modal-cancel')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('#confirm-modal')).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('exports are reachable by keyboard and Escape returns to the trigger', async ({page}) => {
  await login(page);
  const trigger = page.locator('#overview-export-toggle');
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Tab');
  await expect(page.locator('#overview-export-menu button').first()).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(trigger).toBeFocused();
});

test('the saved language applies before sign-in', async ({page}) => {
  await page.addInitScript(() => { localStorage.setItem('ui_lang', 'en'); });
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
});

test('downloaded dashboard CSV cannot execute imported formulas', async ({page}) => {
  await login(page);
  await page.evaluate(() => {
    const table = document.createElement('table');
    const row = table.insertRow();
    for (const value of ['=HYPERLINK("https://attacker.test")', '+cmd', '@SUM(1)', '-cmd']) row.insertCell().textContent = value;
    document.getElementById('overview-content').replaceChildren(table);
  });
  const download = page.waitForEvent('download');
  await inApp(page, app => app.dashExportCurrentTab());
  const file = await download;
  const stream = await file.createReadStream();
  let csv = '';
  for await (const chunk of stream) csv += chunk.toString('utf8');
  expect(csv).toContain('"\'=HYPERLINK(""https://attacker.test"")"');
  for (const value of ['+cmd', '@SUM(1)', '-cmd']) expect(csv).toContain('"\'' + value + '"');
});

for (const theme of ['dark', 'light']) {
  test(`default branding and severity labels retain AA contrast (${theme})`, async ({page}) => {
    await login(page, theme);
    // These are actual theme styles after the settings response has applied.
    await inApp(page, app => app.applyBranding());
    const ratios = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      function rgb(value) { return value.match(/[\d.]+/g).slice(0, 3).map(Number); }
      function lum(c) { return c.map(v => {v /= 255; return v <= .04045 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4);}).reduce((a, v, i) => a + v * [.2126,.7152,.0722][i], 0); }
      function contrast(a, b) {a = lum(a); b = lum(b); return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);}
      const card = document.createElement('div');
      card.className = 'card';
      document.body.appendChild(card);
      const cardBg = rgb(getComputedStyle(card).backgroundColor);
      const values = [];
      const title = document.createElement('span');
      title.className = 'card-title'; card.appendChild(title);
      values.push({cls: "card-title", ratio: contrast(rgb(getComputedStyle(title).color), cardBg)});
      for (const cls of ['sev-critical','sev-high', ...['A','B','C','D','F'].map(g => 'grade-tile grade-'+g), ...['A','B','C','D','F'].map(g => 'grade-hero grade-'+g)]) {
        const el = document.createElement('span'); el.className = cls; card.appendChild(el);
        const css = getComputedStyle(el);
        const rgba = css.backgroundColor.match(/[\d.]+/g).map(Number);
        if (css.backgroundColor.startsWith("color(srgb")) for (let i = 0; i < 3; i++) rgba[i] *= 255;
        const alpha = rgba.length === 4 ? rgba[3] : 1;
        const bg = rgba.slice(0,3).map((v, i) => v * alpha + cardBg[i] * (1-alpha));
        values.push({cls, ratio: contrast(rgb(css.color), bg)});
      }
      card.remove();
      return {blue: root.getPropertyValue('--blue').trim(), values};
    });
    expect(ratios.blue).not.toBe('#0f4c81');
    for (const value of ratios.values) expect(value.ratio, value.cls).toBeGreaterThanOrEqual(4.5);
  });
}

test('network setup title remains readable on a 390px viewport', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await login(page);
  await inApp(page, app => app.openCustomerPage('Browser_Alpha'));
  await page.locator('#cust-tabs [data-tab="nettverk"]').click();
  const title = page.locator('#cust-net-title');
  await expect(title).toBeVisible();
  const size = await title.boundingBox();
  expect(size.width).toBeGreaterThan(80);
  expect(size.height).toBeLessThan(60);
});


test('a custom brand accent adapts to the active theme without weakening button contrast', async ({page}) => {
  await login(page, 'dark');
  await inApp(page, app => app.applyBranding());
  await page.route('**/api/settings', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({branding: {primary_color: '#00cccc'}}),
  }));
  await inApp(page, app => app.applyBranding());
  const accent = () => page.evaluate(() => document.documentElement.style.getPropertyValue('--blue'));
  await expect.poll(accent).toBe('#00cccc');
  // This colour is readable as text on dark cards, but its darkened button
  // is too bright behind white text, so the existing button token remains.
  expect(await page.evaluate(() => document.documentElement.style.getPropertyValue('--blue-btn'))).toBe('');
  await inApp(page, app => app.toggleTheme());
  await expect.poll(accent).toBe('');
  await inApp(page, app => app.toggleTheme());
  await expect.poll(accent).toBe('#00cccc');
});


test('a late branding response cannot override a newer theme request', async ({page}) => {
  await login(page, 'dark');
  await inApp(page, app => app.applyBranding());
  let hits = 0;
  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/settings', async route => {
    const request = ++hits;
    if (request === 1) await held;
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({
      branding: {primary_color: request === 1 ? '#0f4c81' : '#00cccc'},
    })});
  });
  const older = inApp(page, app => app.applyBranding());
  try {
    await expect.poll(() => hits).toBe(1);
    await inApp(page, app => app.applyBranding());
    expect(await page.evaluate(() => document.documentElement.style.getPropertyValue('--blue'))).toBe('#00cccc');
  } finally {
    release();
    await older;
  }
  expect(await page.evaluate(() => document.documentElement.style.getPropertyValue('--blue'))).toBe('#00cccc');
});
