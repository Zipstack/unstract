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

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    /*
     * Asserting the dialog STAYS OPEN, not that a particular message appears.
     * Verified against a running app: submitting this form empty renders no
     * error text at all — the guard is that it refuses to proceed, which is
     * what actually protects against a half-built workflow being created.
     */
    await dialog.getByRole("button", { name: /Create Workflow/i }).click();
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

    const card = page.locator(".list-view-row").first();
    if ((await card.count()) === 0) {
      test.skip(true, "no workflows in this org");
    }
    await card.click();

    const actions = page.getByRole("button", { name: /Actions/i });
    await expect(actions, "workflow detail has no Actions menu").toBeVisible({
      timeout: 20000,
    });

    await actions.click();
    await expect(page.getByRole("menuitem", { name: /Run Workflow/i })).toBeVisible();
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

    const endpoint = page.getByText(/API ENDPOINT/i).first();
    if ((await endpoint.count()) === 0) {
      test.skip(true, "no API deployments in this org");
    }
    await expect(endpoint).toBeVisible();

    // The enable/disable toggle is the control that takes a deployment in and
    // out of service — the single most consequential switch on this page.
    await expect(
      page.locator("[role=switch]").first(),
      "deployment has no enable/disable control",
    ).toBeVisible();
  });
});
