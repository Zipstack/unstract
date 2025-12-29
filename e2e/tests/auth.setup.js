/**
 * Authentication setup for E2E tests
 * Runs before all tests to establish authenticated state
 */
const { test as setup, expect } = require('@playwright/test');
const path = require('path');

const authFile = path.join(__dirname, '../playwright/.auth/user.json');

setup('authenticate', async ({ page }) => {
  // Skip if no credentials provided
  if (!process.env.TEST_USER_EMAIL || !process.env.TEST_USER_PASSWORD) {
    console.log('⚠️ No test credentials provided, skipping auth setup');
    // Create empty auth state for unauthenticated tests
    await page.context().storageState({ path: authFile });
    return;
  }

  // Navigate to login page
  await page.goto('/landing');

  // Wait for login form
  await page.waitForSelector('form', { timeout: 10000 });

  // Fill in credentials
  await page.getByRole('textbox', { name: /email/i }).fill(process.env.TEST_USER_EMAIL);
  await page.getByRole('textbox', { name: /password/i }).fill(process.env.TEST_USER_PASSWORD);

  // Submit login
  await page.getByRole('button', { name: /sign in|login/i }).click();

  // Wait for redirect to dashboard or home page
  await page.waitForURL(`**/${process.env.TEST_ORG_NAME || '*'}/**`, {
    timeout: 30000,
  });

  // Verify logged in state
  await expect(page).not.toHaveURL('/landing');

  // Save authentication state
  await page.context().storageState({ path: authFile });
});
