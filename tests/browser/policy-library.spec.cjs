const {test, expect} = require('@playwright/test');
const {expectSignedIn} = require('./app.cjs');

async function login(page, language = 'en') {
  await page.addInitScript(lang => {
    localStorage.setItem('onboarding_done','1');
    localStorage.setItem('ui_lang',lang);
  }, language);
  await page.goto('/');
  await page.locator('#login-username').fill('browser-admin');
  await page.locator('#login-password').fill('Browser-test123!');
  await page.locator('#login-password').press('Enter');
  await expectSignedIn(page);
  await page.goto('/#/customer/Browser_Alpha/policyer');
  await expect(page.locator('.pl-areas')).toBeVisible();
}

test('policy packages and all service runbooks work before any audit', async ({page}) => {
  await login(page);
  const content = page.locator('#policy-overview-content');
  await expect(content).toContainText('Proposed customer plan; not saved');
  await expect(content.locator('.pl-area')).toHaveCount(9);
  await page.screenshot({path:'/tmp/sybrhub-policy-desktop.png',fullPage:true,animations:'disabled'});
  await content.getByRole('button', {name:'Policy packages',exact:true}).click();
  await expect(content.locator('.pl-package')).toHaveCount(4);
  await content.locator('.pl-package').filter({hasText:'Secure collaboration'}).getByRole('button').click();
  await content.getByRole('button', {name:'Policy library',exact:true}).click();
  await expect(content.locator('.pl-policy')).toHaveCount(39);
  await page.locator('#po-area').selectOption('purview');
  await expect(content.locator('.pl-policy')).toHaveCount(4);
  const dlp = content.locator('[data-policy-id="purview-dlp"]');
  await dlp.locator('summary').click();
  await expect(dlp).toContainText('simulation');
  await expect(dlp).toContainText('Licensing and prerequisites');
  await expect(dlp).toContainText('Verify effectiveness');
  await expect(dlp.getByRole('link',{name:'Microsoft Learn'})).toHaveAttribute('href',/learn.microsoft.com/);
  await page.locator('#po-search').fill('purview-retention');
  await expect(content.locator('.pl-policy')).toHaveCount(1);
  await expect(content).toContainText('Retention does not replace backup');
  await content.getByRole('button',{name:'Captured configuration',exact:true}).click();
  await expect(content).toContainText('not a live check');
  await expect(content.locator('#po-standards')).toContainText('not measured');
});

test('policy drafts survive filters, navigation and a different customer', async ({page}) => {
  await login(page);
  const content = page.locator('#policy-overview-content');
  await content.getByRole('button', {name:'Policy library',exact:true}).click();
  await page.locator('#po-search').fill('ca-mfa');
  const policy = content.locator('[data-policy-id="ca-mfa"]');
  await policy.locator('summary').click();
  await policy.locator('textarea').fill('Synthetic unsaved assessment');
  await policy.locator('select[name="status"]').selectOption('exception');
  await policy.locator('input[name="review_due"]').fill('2027-01-01');
  await expect(page.locator('#po-draft-notice')).toBeVisible();
  await page.locator('#po-tier').selectOption('essential');
  await expect(policy.locator('textarea')).toHaveValue('Synthetic unsaved assessment');
  await expect(policy.locator('select[name="status"]')).toHaveValue('exception');
  await expect(policy.locator('input[name="review_due"]')).toHaveValue('2027-01-01');
  await content.getByRole('button',{name:'Overview',exact:true}).click();
  await content.getByRole('button',{name:'Policy library',exact:true}).click();
  await expect(policy.locator('textarea')).toHaveValue('Synthetic unsaved assessment');
  await page.goto('/#/customer/Browser_Beta/policyer');
  await expect(content.locator('.pl-areas')).toBeVisible();
  await content.getByRole('button',{name:'Policy library',exact:true}).click();
  await expect(content.locator('[data-policy-id="ca-mfa"] textarea')).toHaveValue('');
  await page.goto('/#/customer/Browser_Alpha/policyer');
  await expect(content.locator('.pl-areas')).toBeVisible();
  await content.getByRole('button',{name:'Policy library',exact:true}).click();
  await page.locator('#po-search').fill('ca-mfa');
  await expect(policy.locator('textarea')).toHaveValue('Synthetic unsaved assessment');
  await content.getByRole('button',{name:'Discard draft'}).click();
  await page.locator('#confirm-modal-ok').click();
  await expect(page.locator('#po-draft-notice')).toBeHidden();
});

test('customer plans and evidence survive reload and stale tabs cannot overwrite them', async ({page,context}) => {
  await login(page);
  const sibling = await context.newPage();
  await sibling.goto('/#/customer/Browser_Alpha/policyer');
  await expect(sibling.locator('.pl-areas')).toBeVisible();
  const content = page.locator('#policy-overview-content');
  await content.getByRole('button',{name:'Policy packages',exact:true}).click();
  await content.locator('.pl-package').filter({hasText:'Security foundation'}).getByRole('button').click();
  await content.getByRole('button',{name:'Save customer plan',exact:true}).click();
  await expect(content).toContainText('Saved customer plan');
  await content.getByRole('button',{name:'Policy library',exact:true}).click();
  await page.locator('#po-search').fill('ca-mfa');
  const policy = content.locator('[data-policy-id="ca-mfa"]');
  await policy.locator('summary').click();
  await policy.locator('select[name="status"]').selectOption('aligned');
  const note = 'Pilot group and assignments checked in ticket 42 <script>synthetic</script>';
  await policy.locator('textarea').fill("  " + note + "  ");
  await policy.getByRole('button',{name:'Save assessment'}).click();
  await expect(policy.locator('.pl-policy-head')).toContainText('Verified as aligned');
  await expect(policy.locator('.pl-evidence')).toContainText(note);
  await expect(policy.locator('textarea')).toHaveValue(note);
  await expect(page.locator('#po-draft-notice')).toBeHidden();
  await expect(policy.locator('.pl-evidence script')).toHaveCount(0);
  await sibling.getByRole('button',{name:'Save customer plan',exact:true}).click();
  await expect(sibling.locator('.toast').last()).toContainText('another tab');
  await page.reload();
  await expect(content).toContainText('Saved customer plan');
  await content.getByRole('button',{name:'Policy library',exact:true}).click();
  await page.locator('#po-search').fill('ca-mfa');
  await policy.locator('summary').click();
  await expect(policy.locator('.pl-evidence')).toContainText(note);
  await expect(policy.locator('textarea')).toHaveValue(note);
  // Every write in this flow is local customer-plan storage.
  const response = await page.request.get('/api/policy-overview/Browser_Alpha');
  const plan = (await response.json()).plan;
  expect(plan.package_id).toBe('foundation');
  expect(plan.reviews['ca-mfa'].status).toBe('aligned');
  await sibling.close();
});

test('policy workspace is readable on a narrow screen in Norwegian', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await login(page,'no');
  const content = page.locator('#policy-overview-content');
  await expect(content).toContainText('Policyarbeidsplass');
  await content.locator('[data-area="intune"]').click();
  await expect(page.locator('#po-area')).toHaveValue('intune');
  await expect(content.locator('.pl-policy')).toHaveCount(7);
  const laps = content.locator('[data-policy-id="intune-laps"]');
  await laps.locator('summary').click();
  await expect(laps).toContainText('Anbefalte innstillinger');
  await expect(laps).toContainText('Kontroller effekten');
  const box = await content.boundingBox();
  expect(box.x+box.width).toBeLessThanOrEqual(391);
  await page.screenshot({path:'/tmp/sybrhub-policy-mobile.png',fullPage:true,animations:'disabled'});
});

test('the guided workflow prioritizes the selected plan and opens a pilot runbook', async ({page}) => {
  await login(page);
  const content = page.locator('#policy-overview-content');
  await expect(content).toContainText('Complete the customer policy plan');
  await content.locator('[data-step="actions"]').click();
  await expect(page.locator('#po-status')).toHaveValue('actionable');
  await expect(content.locator('.pl-policy')).not.toHaveCount(0);
  await expect(content).toContainText('CA settings have not been captured');
  await content.getByRole('button',{name:'Overview',exact:true}).click();
  await content.locator('[data-step="pilot"]').click();
  await expect(content.locator('.pl-policy')).toHaveCount(1);
  await expect(content.locator('.pl-policy details')).toHaveAttribute('open','');
  await expect(content).toContainText('Verify effectiveness');
});
