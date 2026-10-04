// The web terminal (xterm.js) under the application policy. xterm's DOM
// renderer puts its theme, font and cell size in <style> elements, which
// style-src-elem 'self' blocks: the terminal drew in the page's font and
// colours, every rewrite of those rules was a policy violation, and A-/A+
// changed nothing on screen. app-infra.js hands xterm a document whose
// <style> lands in a constructed stylesheet instead.
//
// The account is a technician of its own (security.spec enrols browser-tech
// in MFA mid-run), and a technician may not open the hub's local shell: the
// server answers in the terminal and closes, so the terminal opens and draws
// text without a shell being started on the machine running this.
const { test, expect } = require('@playwright/test');
const { expectSignedIn } = require('./app.cjs');

async function login(page) {
  await page.addInitScript(() => {
    localStorage.setItem('onboarding_done', '1');
    localStorage.setItem('ui_lang', 'no');
    window.__cspViolations = [];
    document.addEventListener('securitypolicyviolation', event => {
      window.__cspViolations.push(`${event.violatedDirective} blocked ${event.blockedURI || 'inline'} at ${event.sourceFile}:${event.lineNumber}`);
    });
  });
  await page.goto('/');
  await page.locator('#login-username').fill('browser-term');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expect(page.locator('#login-password')).not.toBeVisible();
  await expectSignedIn(page);
}

async function openTerminal(page) {
  await page.locator('[data-click-handler="showView"][data-view="terminal"]').first().evaluate(el => el.click());
  await expect(page.locator('#view-terminal')).toHaveClass(/\bactive\b/);
  await page.locator('#term-connect-btn').click();
  // The server's refusal, drawn by the terminal.
  await expect(page.locator('#term-container .xterm-rows')).toContainText('admin');
}

const rows = page => page.locator('#term-container .xterm-rows');
const look = el => {
  const s = getComputedStyle(el);
  return {size: s.fontSize, family: s.fontFamily, colour: s.color, line: el.firstElementChild.getBoundingClientRect().height};
};
const violations = page => page.evaluate(() => window.__cspViolations.slice());

test('the terminal draws in its own font and colours, and A+ and A- resize it, with no policy violation', async ({page}) => {
  await login(page);
  await openTerminal(page);
  const start = await rows(page).evaluate(look);
  expect(start.size).toBe('14px');
  expect(start.family).toContain('monospace');
  expect(start.colour).toBe('rgb(230, 237, 243)');   // the theme's foreground, not the page's text colour
  await expect(page.locator('#term-container style')).toHaveCount(0);

  await page.locator('[data-click-handler="termChangeFontSize"][data-delta="1"]').click();
  await expect.poll(() => rows(page).evaluate(look).then(l => l.size)).toBe('15px');
  expect((await rows(page).evaluate(look)).line).toBeGreaterThan(start.line);
  expect(await page.evaluate(() => localStorage.getItem('sybr_term_fontsize'))).toBe('15');

  await page.locator('[data-click-handler="termChangeFontSize"][data-delta="-1"]').click();
  await page.locator('[data-click-handler="termChangeFontSize"][data-delta="-1"]').click();
  await expect.poll(() => rows(page).evaluate(look).then(l => l.size)).toBe('13px');

  expect(await violations(page)).toEqual([]);
});

test('the terminal opens at the size this browser chose last', async ({page}) => {
  await login(page);
  await page.evaluate(() => localStorage.setItem('sybr_term_fontsize', '18'));
  await page.reload();
  await expectSignedIn(page);
  await openTerminal(page);
  expect((await rows(page).evaluate(look)).size).toBe('18px');
  // Nonsense in storage is ignored, not drawn.
  await page.evaluate(() => localStorage.setItem('sybr_term_fontsize', 'huge'));
  await page.reload();
  await expectSignedIn(page);
  await openTerminal(page);
  expect((await rows(page).evaluate(look)).size).toBe('14px');
  expect(await violations(page)).toEqual([]);
});
