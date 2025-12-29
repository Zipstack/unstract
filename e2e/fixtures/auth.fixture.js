/**
 * Authentication fixtures for E2E tests
 * Provides authenticated browser context for tests
 */
const { test as base } = require('@playwright/test');

/**
 * Extended test fixture with authentication
 */
exports.test = base.extend({
  // Authenticated page fixture
  authenticatedPage: async ({ browser }, use) => {
    // Create a new browser context
    const context = await browser.newContext({
      storageState: 'playwright/.auth/user.json',
    });

    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  // Admin authenticated page fixture
  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: 'playwright/.auth/admin.json',
    });

    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

exports.expect = base.expect;
