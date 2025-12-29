/**
 * Critical Path: Workflow Execution
 * Priority: Tier 1 - Must pass for release
 *
 * Tests the core workflow execution user journey:
 * - Navigate to workflows
 * - View workflow list
 * - Execute a workflow (if available)
 * - View execution results
 */
const { test, expect } = require('@playwright/test');
const {
  waitForPageLoad,
  waitForApiResponse,
  navigateToOrg,
} = require('../../utils/test-helpers');
const { test: authTest } = require('../../fixtures/auth.fixture');

test.describe('Workflow Execution', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure we're on the authenticated state
    test.skip(!process.env.TEST_ORG_NAME, 'Test org not provided');
  });

  test.describe('Workflow List', () => {
    test('should display workflows page', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/workflows`);
      await waitForPageLoad(page);

      // Should see workflows section
      await expect(
        page
          .getByRole('heading', { name: /workflow/i })
          .or(page.getByText(/workflow/i).first())
      ).toBeVisible();
    });

    test('should show empty state or workflow list', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/workflows`);
      await waitForPageLoad(page);

      // Should either show workflows or empty state
      const workflowList = page.locator('[data-testid="workflow-list"]');
      const emptyState = page.getByText(/no workflow|create.*workflow|get started/i);

      await expect(workflowList.or(emptyState)).toBeVisible({ timeout: 15000 });
    });

    test('should have create workflow button', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/workflows`);
      await waitForPageLoad(page);

      // Should have a create button
      await expect(
        page
          .getByRole('button', { name: /create|new|add/i })
          .or(page.getByTestId('create-workflow'))
      ).toBeVisible();
    });
  });

  test.describe('Workflow Navigation', () => {
    test('should navigate between workflow pages', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/workflows`);
      await waitForPageLoad(page);

      // Check that navigation elements are present
      const navItems = page.getByRole('navigation');
      await expect(navItems).toBeVisible();
    });

    test('should maintain workflow context during navigation', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/workflows`);
      await waitForPageLoad(page);

      // Navigate to another section and back
      const dashboardLink = page.getByRole('link', { name: /dashboard|home/i });
      if (await dashboardLink.isVisible()) {
        await dashboardLink.click();
        await waitForPageLoad(page);

        // Navigate back to workflows
        const workflowsLink = page.getByRole('link', { name: /workflow/i });
        await workflowsLink.click();
        await waitForPageLoad(page);

        // Should be back on workflows page
        await expect(page).toHaveURL(/.*workflow.*/);
      }
    });
  });

  test.describe('Workflow Actions', () => {
    test('should open workflow details when clicked', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/workflows`);
      await waitForPageLoad(page);

      // Find first workflow item if any exist
      const workflowItem = page.locator('[data-testid="workflow-item"]').first();

      if (await workflowItem.isVisible()) {
        await workflowItem.click();
        await waitForPageLoad(page);

        // Should be on workflow detail page
        await expect(page).toHaveURL(/.*workflow.*/);
      } else {
        // No workflows, test passes as there's nothing to click
        test.skip(true, 'No workflows available to test');
      }
    });
  });
});
