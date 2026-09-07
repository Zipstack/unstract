import { expect, test } from "./fixtures.js";

/**
 * Prompt Studio — the app's primary authoring surface.
 *
 * Covers the `prompt-studio-author` critical path from the UI side: a user can
 * reach the listing, open the create-project form, and the form enforces its
 * required fields. The API-side equivalent lives in tests/e2e/prompt_studio.
 *
 * Scope is deliberately narrow. Per tests/critical_paths.yaml: "We
 * intentionally do NOT chase 100% coverage." These assert that the critical
 * affordances exist and respond, not that every control is pixel-correct.
 */
test.describe("prompt studio", () => {
  test("the listing loads and offers project creation", async ({ page, app }) => {
    await app.goto("tools");

    await expect(
      page.getByRole("button", { name: /New Project/i }),
      "no way to create a project",
    ).toBeVisible();
  });

  /*
   * The create form is the entry point to `prompt-studio-author`. Asserting
   * that it validates — rather than that a project can be created — keeps the
   * test read-only, so it can run against any environment without leaving
   * fixtures behind.
   */
  test("the create-project form requires its mandatory fields", async ({
    page,
    app,
  }) => {
    await app.goto("tools");
    await page.getByRole("button", { name: /New Project/i }).click();

    const dialog = page.getByTestId("add-prompt-project-modal");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/Prompt Studio project name/i)).toBeVisible();

    /*
     * Submitting empty must surface field errors and keep the dialog open,
     * not silently close or POST a half-built project.
     *
     * The message asserted here is the SERVER's ("This field may not be
     * blank."), verified against a running app — the client-side string in
     * AddCustomToolFormModal.jsx never renders, because the submit reaches the
     * API before antd's own validation shows.
     */
    // The footer button reads "Save" here and "Update" in the edit flow, so
    // its id is the stable handle, not its label.
    await dialog.getByTestId("add-prompt-project-modal-ok").click();
    await expect(
      dialog.getByText(/may not be blank/i).first(),
    ).toBeVisible();
    await expect(dialog).toBeVisible();
  });

  /*
   * Opening a project is the gateway to every prompt operation. The Document
   * Parser tab is the authoring surface itself, so its absence means the
   * project failed to load rather than merely rendering oddly.
   */
  test("an existing project opens on the Document Parser", async ({
    page,
    app,
  }) => {
    await app.goto("tools");

    /*
     * Was `.list-view-row`, which stopped matching anything when the listing
     * moved to ResourceTable — so this test silently SKIPPED rather than
     * failing. Rows now carry an id minted from the project's tool_id.
     */
    const project = page
      .locator('[data-testid^="prompt-studio-list-row-"]')
      .first();
    if ((await project.count()) === 0) {
      test.skip(true, "no prompt studio projects in this org");
    }
    await project.click();

    await expect(
      page.getByText("Document Parser").first(),
      "project did not open on its authoring surface",
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("Combined Output").first()).toBeVisible();
  });
});
