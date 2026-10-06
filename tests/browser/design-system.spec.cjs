// The design system the markup is built on: one tab bar, colours from tokens
// through classes, and the one value a class cannot carry (a bar's length)
// set without a style attribute in the markup.
const { test, expect } = require('@playwright/test');
const { inApp, expectSignedIn } = require('./app.cjs');

async function login(page, theme = 'dark') {
  await page.addInitScript(t => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
    localStorage.setItem('sybr-theme', t);
  }, theme);
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

const tabLook = el => {
  const s = getComputedStyle(el);
  return [s.fontSize, s.paddingTop, s.paddingLeft, s.borderBottomWidth].join(' ');
};

test('every tab bar is the same tab bar', async ({page}) => {
  await login(page);
  const overview = await page.locator('#view-overview .tab').first().evaluate(tabLook);
  await inApp(page, app => app.showView('network'));
  const network = await page.locator('#view-network .tab').first().evaluate(tabLook);
  await inApp(page, app => app.openCustomerPage('Browser_Beta'));
  await expect(page.locator('#cust-tabs .tab.active')).toBeVisible();
  const customer = await page.locator('#cust-tabs .tab').first().evaluate(tabLook);
  expect(network).toBe(overview);
  expect(customer).toBe(overview);
});

test('a bar takes its length from data-bar, with no style attribute in the markup', async ({page}) => {
  await login(page);
  const width = await page.evaluate(async () => {
    const box = document.createElement('div');
    box.innerHTML = '<div class="bar" style="width:200px"><div class="bar-fill" data-bar="40"></div></div>';
    document.body.appendChild(box);
    await new Promise(r => setTimeout(r, 50));
    const fill = box.querySelector('.bar-fill');
    const out = {value: fill.style.getPropertyValue('--bar-value'), width: fill.getBoundingClientRect().width};
    box.remove();
    return out;
  });
  expect(width.value).toBe('40%');
  expect(Math.round(width.width)).toBe(80);
});

test('a colour a script picks becomes the class that paints it', async ({page}) => {
  await login(page);
  const tones = await inApp(page, app => [
    app.toneClass('var(--green)'), app.toneClass('#f85149'), app.toneClass('var(--orange)'),
    app.toneClass('var(--text-dim)'), app.toneClass('nonsense'), app.badgeClass('var(--red)'), app.badgeClass(''),
  ]);
  expect(tones).toEqual(['text-success', 'text-danger', 'text-warning', 'text-dim', '', 'badge badge-danger', 'badge']);
});

test('Varsler filters are pills, not the findings severity label', async ({page}) => {
  await login(page);
  await inApp(page, app => app.openOverviewTab('dash-alerts'));
  const chip = page.locator('#dash-alerts-content .filter-chip').first();
  await expect(chip).toBeVisible();
  const look = await chip.evaluate(el => {
    const s = getComputedStyle(el);
    return {radius: parseFloat(s.borderTopLeftRadius), height: el.getBoundingClientRect().height};
  });
  expect(look.radius).toBeGreaterThanOrEqual(look.height / 2);
});

for (const theme of ['dark', 'light']) {
  test(`the grade on the customer page is drawn in the theme's colour (${theme})`, async ({page}) => {
    await login(page, theme);
    await inApp(page, app => app.openCustomerPage('Browser_Beta'));
    const hero = page.locator('.grade-hero');
    await expect(hero).toHaveText('C');
    const [bg, orange] = await hero.evaluate(el => {
      const probe = document.createElement('span');
      probe.style.color = 'var(--orange-btn)';
      document.body.appendChild(probe);
      const want = getComputedStyle(probe).color;
      probe.remove();
      return [getComputedStyle(el).backgroundColor, want];
    });
    expect(bg).toBe(orange);
  });
}
