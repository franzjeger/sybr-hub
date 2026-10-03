const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
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
  // rest, in a project of their own.
  projects: [
    {name: 'shared', testIgnore: /modules\.spec\.cjs$/},
    {name: 'server-settings', testMatch: /modules\.spec\.cjs$/, dependencies: ['shared']},
  ],
  webServer: {
    command: (process.env.SYBR_TEST_PYTHON || '.venv/bin/python') + ' tests/browser/server.py',
    url: 'http://127.0.0.1:18099/api/health',
    reuseExistingServer: false,
    timeout: 30000
  }
});
