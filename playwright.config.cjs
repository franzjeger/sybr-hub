const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  forbidOnly: !!process.env.CI,
  testDir: './tests/browser',
  timeout: 30000,
  fullyParallel: false,
  use: {
    baseURL: 'http://127.0.0.1:18099',
    headless: true,
    launchOptions: process.env.SYBR_TEST_CHROMIUM ? {executablePath: process.env.SYBR_TEST_CHROMIUM} : {}
  },
  reporter: 'list',
  // Specs share one fixture server. modules.spec switches the AI module off
  // for a moment, and any spec that read the Verktøy menu at that moment saw
  // no Sybrt and failed. Specs that change server-wide settings run after the
  // rest, in a project of their own. network-setup gives Browser Beta a
  // FortiGate for a moment, which a fleet poll from another spec reads (and
  // records its firmware, which Varsler counts); scheduler-customer sets the
  // automatic audit's customer.
  projects: [
    {name: 'shared', testIgnore: /(modules|network-setup|scheduler-customer)\.spec\.cjs$/},
    {name: 'server-settings', testMatch: /(modules|network-setup|scheduler-customer)\.spec\.cjs$/, dependencies: ['shared']},
  ],
  webServer: {
    command: (process.env.SYBR_TEST_PYTHON || '.venv/bin/python') + ' tests/browser/server.py',
    url: 'http://127.0.0.1:18099/api/health',
    reuseExistingServer: false,
    timeout: 30000
  }
});
