const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: 'preview.spec.cjs', fullyParallel: false,
  workers: 1, retries: 0, forbidOnly: true, timeout: 15000,
  outputDir: process.env.COSMOS_UI_OUTPUT,
  reporter: [['./reporter.cjs']],
  use: { browserName: 'chromium', headless: true, viewport: { width: 1100, height: 780 },
    locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light', trace: 'retain-on-failure' }
});
