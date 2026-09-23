import { expect, test } from "./fixtures.js";

/**
 * Workflows — authoring and the API-deployment surface.
 *
 * Covers the UI side of `workflow-author` and `api-deployment-provision`. The
 * execution half (`workflow-create-execute`) is API-driven and already lives in
 * tests/e2e/workflows; duplicating it through a browser would be slower and
 * flakier for no extra signal.
 */
test.describe("workflows", () => {
  test("the listing loads and offers workflow creation", async ({
    page,
    app,
  }) => {
    await app.goto("workflows");

    await expect(
      page.getByRole("button", { name: /New Workflow/i }),
      "no way to create a workflow",
    ).toBeVisible();
  });

  /*
   * Read-only check of the `workflow-author` entry point: the form opens and
   * enforces its required fields, so a half-built workflow cannot be POSTed.
   */
  test("the create-workflow form requires its mandatory fields", async ({
    page,
    app,
  }) => {
    await app.goto("workflows");
    await page.getByRole("button", { name: /New Workflow/i }).click();

    const dialog = page.getByTestId("new-workflow-modal");
    await expect(dialog).toBeVisible();

    /*
     * Asserting the dialog STAYS OPEN, not that a particular message appears.
     * Verified against a running app: submitting this form empty renders no
     * error text at all — the guard is that it refuses to proceed, which is
     * what actually protects against a half-built workflow being created.
     */
    // "Create Workflow" here, "Edit Workflow" in the edit flow — same button.
    await dialog.getByTestId("new-workflow-modal-ok").click();
    await expect(dialog, "empty form was accepted").toBeVisible();
    await expect(page).toHaveURL(/\/workflows(\/|$|\?)/);
  });

  /*
   * Opening a workflow must reach its builder. The Actions menu is the entry
   * point for running it and for viewing file history, so its presence is the
   * cheapest proof the detail page wired up rather than half-rendering.
   */
  test("a workflow opens and exposes its actions", async ({ page, app }) => {
    await app.goto("workflows");

    // Was `.list-view-row` — dead since the ResourceTable migration, which
    // made this test skip instead of fail. See prompt-studio.spec.js.
    const card = page.locator('[data-testid^="workflow-list-row-"]').first();
    if ((await card.count()) === 0) {
      test.skip(true, "no workflows in this org");
    }
    await card.click();

    const actions = page.getByTestId("workflow-actions-btn");
    await expect(actions, "workflow detail has no Actions menu").toBeVisible({
      timeout: 20000,
    });

    // The menu is portalled; its entries derive their ids from the Dropdown's.
    await actions.click();
    await expect(
      page.getByTestId("workflow-actions-item-run-workflow"),
    ).toBeVisible();
  });
});

/**
 * API deployments — `api-deployment-provision` from the UI side.
 *
 * The deployment's endpoint and key are what downstream callers depend on, so
 * the listing surfacing them is the thing worth guarding here. Actually calling
 * the endpoint is covered API-side in tests/e2e/api_deployment.
 */
test.describe("api deployments", () => {
  test("the listing loads and offers a new deployment", async ({
    page,
    app,
  }) => {
    await app.goto("api");

    await expect(
      page.getByRole("button", { name: /API Deployment/i }).first(),
      "no way to create an API deployment",
    ).toBeVisible();
  });

  test("a deployment exposes its endpoint and management controls", async ({
    page,
    app,
  }) => {
    await app.goto("api");

    /*
     * Scope to ONE deployment card rather than taking `.first()` of a
     * page-wide `[role=switch]`: that locator would happily match a switch
     * belonging to a different card, or to no card at all.
     */
    const card = page
      .locator('[data-testid^="api-deployment-list-card-"]')
      .first();
    if ((await card.count()) === 0) {
      test.skip(true, "no API deployments in this org");
    }

    await expect(card.getByText(/API Endpoint/i).first()).toBeVisible();

    // The enable/disable toggle is the control that takes a deployment in and
    // out of service — the single most consequential switch on this page.
    await expect(
      card.locator('[data-testid^="api-deployment-toggle-"]'),
      "deployment has no enable/disable control",
    ).toBeVisible();
  });
});
