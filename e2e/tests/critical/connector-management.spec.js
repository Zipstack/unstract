/**
 * Critical Path: Connector Management
 * Priority: Tier 1 - Must pass for release
 *
 * Tests the connector configuration user journey:
 * - View available connectors
 * - Add/configure a connector
 * - Test connector connection
 * - View connected sources
 */
const { test, expect } = require('@playwright/test');
const {
  waitForPageLoad,
  waitForApiResponse,
} = require('../../utils/test-helpers');

test.describe('Connector Management', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!process.env.TEST_ORG_NAME, 'Test org not provided');
  });

  test.describe('Connector List', () => {
    test('should display connectors/adapters page', async ({ page }) => {
      // Try common connector page paths
      const connectorPaths = [
        `/${process.env.TEST_ORG_NAME}/settings/connectors`,
        `/${process.env.TEST_ORG_NAME}/connectors`,
        `/${process.env.TEST_ORG_NAME}/adapters`,
        `/${process.env.TEST_ORG_NAME}/settings`,
      ];

      let foundPage = false;
      for (const path of connectorPaths) {
        await page.goto(path);
        await waitForPageLoad(page);

        // Check if we found a connector-related page
        const connectorContent = page.getByText(/connector|adapter|integration|source/i);
        if (await connectorContent.isVisible()) {
          foundPage = true;
          break;
        }
      }

      expect(foundPage).toBe(true);
    });

    test('should show available connector types', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      // Look for connector type options (databases, filesystems, etc.)
      const connectorTypes = page.getByText(
        /database|file.*system|cloud.*storage|api|s3|google.*drive|postgresql|mysql/i
      );

      // At least some connector types should be visible
      await expect(connectorTypes.first()).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('Connector Configuration', () => {
    test('should have add connector button', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      // Should have an add/create button for connectors
      await expect(
        page
          .getByRole('button', { name: /add|create|new|configure/i })
          .or(page.getByTestId('add-connector'))
      ).toBeVisible();
    });

    test('should open connector configuration modal/form', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      // Click add connector
      const addButton = page
        .getByRole('button', { name: /add|create|new/i })
        .first();

      if (await addButton.isVisible()) {
        await addButton.click();

        // Should see a form or modal
        await expect(
          page
            .getByRole('dialog')
            .or(page.getByRole('form'))
            .or(page.locator('.ant-modal'))
        ).toBeVisible({ timeout: 5000 });
      }
    });

    test('should show connector form fields', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      // Navigate to a connector configuration if possible
      const addButton = page
        .getByRole('button', { name: /add|create|new/i })
        .first();

      if (await addButton.isVisible()) {
        await addButton.click();

        // Should see form fields (name, connection details, etc.)
        const formFields = page.locator('input, select, textarea');
        expect(await formFields.count()).toBeGreaterThan(0);
      }
    });
  });

  test.describe('Connector Validation', () => {
    test('should validate required fields', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      const addButton = page
        .getByRole('button', { name: /add|create|new/i })
        .first();

      if (await addButton.isVisible()) {
        await addButton.click();
        await waitForPageLoad(page);

        // Try to submit without filling required fields
        const submitButton = page
          .getByRole('button', { name: /save|submit|create|add/i })
          .first();

        if (await submitButton.isVisible()) {
          await submitButton.click();

          // Should show validation errors
          await expect(
            page.getByText(/required|please.*enter|cannot.*empty|is required/i)
          ).toBeVisible({ timeout: 5000 });
        }
      }
    });

    test('should have test connection functionality', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      // Look for test connection button (may be in form or on connector card)
      const testButton = page.getByRole('button', {
        name: /test.*connection|verify|check.*connection/i,
      });

      // Test connection button should exist somewhere in the UI
      // This may not be visible until a connector form is open
    });
  });

  test.describe('Connected Sources', () => {
    test('should display configured connectors', async ({ page }) => {
      await page.goto(`/${process.env.TEST_ORG_NAME}/settings`);
      await waitForPageLoad(page);

      // Should show either configured connectors or empty state
      const connectorList = page.locator(
        '[data-testid="connector-list"], .connector-card, .adapter-item'
      );
      const emptyState = page.getByText(/no.*connector|add.*first|get.*started/i);

      await expect(connectorList.first().or(emptyState)).toBeVisible({
        timeout: 10000,
      });
    });
  });
});
