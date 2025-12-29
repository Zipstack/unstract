/**
 * Critical Path: Authentication Flow
 * Priority: Tier 1 - Must pass for release
 *
 * Tests the core authentication user journey:
 * - Login with valid credentials
 * - Session persistence
 * - Logout functionality
 * - Protected route access
 */
const { test, expect } = require('@playwright/test');
const { waitForPageLoad, login, logout } = require('../../utils/test-helpers');

test.describe('Authentication Flow', () => {
  test.describe('Login', () => {
    test('should display login page for unauthenticated users', async ({ page }) => {
      await page.goto('/landing');
      await waitForPageLoad(page);

      // Verify login form is present
      await expect(page.getByRole('textbox', { name: /email/i })).toBeVisible();
      await expect(page.getByRole('textbox', { name: /password/i })).toBeVisible();
      await expect(page.getByRole('button', { name: /sign in|login/i })).toBeVisible();
    });

    test('should redirect to landing when accessing protected route unauthenticated', async ({
      page,
    }) => {
      // Try to access a protected route directly
      await page.goto('/test-org/dashboard');
      await waitForPageLoad(page);

      // Should be redirected to landing
      await expect(page).toHaveURL(/.*landing.*/);
    });

    test('should show error message for invalid credentials', async ({ page }) => {
      await page.goto('/landing');

      // Fill in invalid credentials
      await page.getByRole('textbox', { name: /email/i }).fill('invalid@example.com');
      await page.getByRole('textbox', { name: /password/i }).fill('wrongpassword');
      await page.getByRole('button', { name: /sign in|login/i }).click();

      // Should show error message
      await expect(
        page.getByText(/invalid|incorrect|failed|error/i)
      ).toBeVisible({ timeout: 10000 });

      // Should still be on login page
      await expect(page).toHaveURL(/.*landing.*/);
    });

    test('should login successfully with valid credentials', async ({ page }) => {
      // Skip if no test credentials
      test.skip(
        !process.env.TEST_USER_EMAIL || !process.env.TEST_USER_PASSWORD,
        'Test credentials not provided'
      );

      await login(page, process.env.TEST_USER_EMAIL, process.env.TEST_USER_PASSWORD);

      // Should be redirected away from landing
      await expect(page).not.toHaveURL(/.*landing.*/);

      // Verify user is logged in (check for user menu or dashboard element)
      await expect(
        page.getByTestId('user-menu').or(page.getByRole('navigation'))
      ).toBeVisible();
    });

    test('should validate email format', async ({ page }) => {
      await page.goto('/landing');

      // Try invalid email format
      await page.getByRole('textbox', { name: /email/i }).fill('not-an-email');
      await page.getByRole('textbox', { name: /password/i }).fill('somepassword');
      await page.getByRole('button', { name: /sign in|login/i }).click();

      // Should show validation error or not submit
      // Either error message or still on page
      await expect(page).toHaveURL(/.*landing.*/);
    });
  });

  test.describe('Session Management', () => {
    test('should maintain session after page reload', async ({ page }) => {
      test.skip(
        !process.env.TEST_USER_EMAIL || !process.env.TEST_USER_PASSWORD,
        'Test credentials not provided'
      );

      await login(page, process.env.TEST_USER_EMAIL, process.env.TEST_USER_PASSWORD);

      // Reload page
      await page.reload();
      await waitForPageLoad(page);

      // Should still be logged in
      await expect(page).not.toHaveURL(/.*landing.*/);
    });

    test('should redirect to correct org after login', async ({ page }) => {
      test.skip(
        !process.env.TEST_USER_EMAIL || !process.env.TEST_USER_PASSWORD || !process.env.TEST_ORG_NAME,
        'Test credentials or org not provided'
      );

      await login(page, process.env.TEST_USER_EMAIL, process.env.TEST_USER_PASSWORD);

      // Should be on the correct org's page
      await expect(page).toHaveURL(new RegExp(`.*${process.env.TEST_ORG_NAME}.*`));
    });
  });

  test.describe('Logout', () => {
    test('should logout successfully', async ({ page }) => {
      test.skip(
        !process.env.TEST_USER_EMAIL || !process.env.TEST_USER_PASSWORD,
        'Test credentials not provided'
      );

      // Login first
      await login(page, process.env.TEST_USER_EMAIL, process.env.TEST_USER_PASSWORD);

      // Logout
      await logout(page);

      // Should be redirected to landing
      await expect(page).toHaveURL(/.*landing.*/);
    });

    test('should not access protected routes after logout', async ({ page }) => {
      test.skip(
        !process.env.TEST_USER_EMAIL || !process.env.TEST_USER_PASSWORD,
        'Test credentials not provided'
      );

      // Login
      await login(page, process.env.TEST_USER_EMAIL, process.env.TEST_USER_PASSWORD);

      // Get current URL to try to access later
      const protectedUrl = page.url();

      // Logout
      await logout(page);

      // Try to access the protected URL
      await page.goto(protectedUrl);
      await waitForPageLoad(page);

      // Should be redirected to landing
      await expect(page).toHaveURL(/.*landing.*/);
    });
  });
});
