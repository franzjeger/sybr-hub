// Controls that open something close it again, and say which state they are
// in. Each of these only ever opened: the overview row's ⋯ menu, the
// customer page's "Endre tags", and Oversikt's auto-refresh, which also kept
// saying "on" after leaving the page had stopped it.
const { test, expect } = require('@playwright/test');
const { expectSignedIn } = require('./app.cjs');

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

test('the overview row menu opens on the first click and closes on the second', async ({page}) => {
  // Signing in, the address and the tab each load the overview, and each
  // load draws the table again, closing any menu: the clicks wait for the last.
  let loading = 0;
  const overview = r => new URL(r.url()).pathname === '/api/dashboard/overview';
  page.on('request', r => { if (overview(r)) loading++; });
  page.on('requestfinished', r => { if (overview(r)) loading--; });
  page.on('requestfailed', r => { if (overview(r)) loading--; });
  await login(page);
  await page.evaluate(() => { location.hash = '#/overview'; });
  await page.locator('#view-overview .tab[data-tab="dash-customers"]').click();
  const row = page.locator('.customer-overview-table tbody tr', {hasText: 'Browser Beta'});
  const toggle = row.locator('[data-click-handler="dashToggleRowActions"]');
  const menu = row.locator('.row-actions-menu');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect.poll(() => loading).toBe(0);
  await page.locator('.customer-overview-table').evaluate(table => { table.dataset.specDrawn = '1'; });

  await toggle.click();
  await expect(menu).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');

  await toggle.click();
  await expect(menu).toBeHidden();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');

  // Another row's menu closes this one (clicked in script: the open menu
  // covers the rows below it, as a menu does).
  await toggle.click();
  const other = page.locator('.customer-overview-table tbody tr', {hasText: 'Browser Alpha'});
  await other.locator('[data-click-handler="dashToggleRowActions"]').evaluate(el => el.click());
  await expect(other.locator('.row-actions-menu')).toBeVisible();
  await expect(menu).toBeHidden();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');

  // And a click outside closes whichever is open.
  await page.locator('#view-overview').evaluate(el => el.click());
  await expect(other.locator('.row-actions-menu')).toBeHidden();
  // All on the table drawn before the first click, not on a redrawn one.
  await expect(page.locator('.customer-overview-table')).toHaveAttribute('data-spec-drawn', '1');
});

test('Endre tags opens the editor, closes it, and reopens it with the tags saved since', async ({page}) => {
  // The saves are answered here, so the fixture's customer keeps no tags.
  const saved = [];
  await page.route('**/api/customer/Browser_Alpha/tags', route => {
    saved.push(route.request().postDataJSON().tags);
    return route.fulfill({json: {ok: true}});
  });
  await login(page);
  await page.evaluate(() => { location.hash = '#/customer/Browser_Alpha/detaljer'; });
  const panel = page.locator('#cust-panel-detaljer');
  const button = panel.getByRole('button', {name: 'Endre tags'});
  const editor = panel.locator('.cust-tag-editor');
  await expect(button).toHaveAttribute('aria-expanded', 'false');

  await button.click();
  await expect(editor).toBeVisible();
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await editor.locator('.tag-input').fill('Kunde A-tag');
  await editor.locator('[data-click-handler="addTagFromInput"]').click();
  await expect.poll(() => saved.length).toBe(1);
  expect(saved[0]).toEqual(['Kunde A-tag']);

  await button.click();
  await expect(editor).toBeHidden();
  await expect(button).toHaveAttribute('aria-expanded', 'false');

  // Reopened, the editor starts from what was saved, so the next tag is
  // added to it instead of replacing it.
  await button.click();
  await expect(editor).toBeVisible();
  await expect(editor).toContainText('Kunde A-tag');
  await editor.locator('[data-click-handler="addSuggestedTag"][data-tag="Premium"]').click();
  await expect.poll(() => saved.length).toBe(2);
  expect(saved[1]).toEqual(['Kunde A-tag', 'Premium']);
});

test('Oversikt\'s auto-refresh lights while on, and is off again after leaving the page', async ({page}) => {
  await login(page);
  await page.evaluate(() => { location.hash = '#/overview'; });
  const button = page.locator('#dash-autorefresh-btn');
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  const glyph = await button.textContent();

  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(button).toHaveClass(/\baccent\b/);
  // Still the ↻ it was, not a sentence squeezed into the tab bar.
  await expect(button).toHaveText(glyph);

  await page.evaluate(() => { location.hash = '#/customers'; });
  await expect(page.locator('#view-customers')).toHaveClass(/\bactive\b/);
  await page.evaluate(() => { location.hash = '#/overview'; });
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  await expect(button).not.toHaveClass(/\baccent\b/);

  await button.click();
  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'false');
});
