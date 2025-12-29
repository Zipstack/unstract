/**
 * Common test helper utilities for E2E tests
 */

/**
 * Wait for page to be fully loaded
 * @param {import('@playwright/test').Page} page
 */
async function waitForPageLoad(page) {
  await page.waitForLoadState('networkidle');
  await page.waitForLoadState('domcontentloaded');
}

/**
 * Login helper for authentication
 * @param {import('@playwright/test').Page} page
 * @param {string} email
 * @param {string} password
 */
async function login(page, email, password) {
  await page.goto('/landing');
  await page.getByRole('textbox', { name: /email/i }).fill(email);
  await page.getByRole('textbox', { name: /password/i }).fill(password);
  await page.getByRole('button', { name: /sign in|login/i }).click();
  await waitForPageLoad(page);
}

/**
 * Logout helper
 * @param {import('@playwright/test').Page} page
 */
async function logout(page) {
  // Click user menu/avatar
  await page.getByTestId('user-menu').click();
  await page.getByRole('menuitem', { name: /logout|sign out/i }).click();
  await waitForPageLoad(page);
}

/**
 * Navigate to a specific organization
 * @param {import('@playwright/test').Page} page
 * @param {string} orgName
 */
async function navigateToOrg(page, orgName) {
  await page.goto(`/${orgName}/dashboard`);
  await waitForPageLoad(page);
}

/**
 * Wait for toast notification
 * @param {import('@playwright/test').Page} page
 * @param {string} message - Expected message (partial match)
 * @param {'success'|'error'|'info'|'warning'} type
 */
async function waitForToast(page, message, type = 'success') {
  const toastSelector = `.ant-message-${type}`;
  await page.waitForSelector(toastSelector);
  await page.getByText(message).waitFor({ state: 'visible' });
}

/**
 * Take a named screenshot for debugging
 * @param {import('@playwright/test').Page} page
 * @param {string} name
 */
async function debugScreenshot(page, name) {
  if (process.env.DEBUG_SCREENSHOTS === 'true') {
    await page.screenshot({ path: `test-results/debug-${name}.png` });
  }
}

/**
 * Wait for API response
 * @param {import('@playwright/test').Page} page
 * @param {string} urlPattern - URL pattern to match
 * @param {number} status - Expected status code
 */
async function waitForApiResponse(page, urlPattern, status = 200) {
  return page.waitForResponse(
    (response) =>
      response.url().includes(urlPattern) && response.status() === status
  );
}

/**
 * Mock API response for testing
 * @param {import('@playwright/test').Page} page
 * @param {string} urlPattern
 * @param {Object} responseBody
 */
async function mockApiResponse(page, urlPattern, responseBody) {
  await page.route(`**${urlPattern}`, (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(responseBody),
    });
  });
}

module.exports = {
  waitForPageLoad,
  login,
  logout,
  navigateToOrg,
  waitForToast,
  debugScreenshot,
  waitForApiResponse,
  mockApiResponse,
};
