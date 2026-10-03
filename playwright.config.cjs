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
  webServer: {
    command: (process.env.SYBR_TEST_PYTHON || '.venv/bin/python') + ' tests/browser/server.py',
    url: 'http://127.0.0.1:18099/api/health',
    reuseExistingServer: false,
    timeout: 30000
  }
});
