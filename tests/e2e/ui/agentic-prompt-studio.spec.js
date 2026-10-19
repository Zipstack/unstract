import { expect, test } from "./fixtures.js";

/**
 * Agentic Prompt Studio — listing and the project authoring surface.
 *
 * The critical path here is the one that broke: listing → open a project → the
 * authoring surface renders. Opening a project died with "Couldn't load this
 * page" because the Skeleton shim never defined `<Skeleton.Button>`, and an
 * undefined element type takes down the whole route.
 *
 * That class of failure is invisible to the vitest suite unless something
 * renders the exact sub-component, and it is invisible to `shim-completeness`
 * because that guard scans OSS `src/` while these plugins live in a gitignored
 * tree. A browser opening the real page is what catches it.
 */

/** Open the first project, or skip when the org has none. */
async function openFirstProject(page, app) {
  await app.goto("agentic-prompt-studio/projects");

  /*
   * Was `.list-view-row, .ant-list-item` — neither exists any more, so this
   * skipped rather than failed rather than surfacing anything.
   */
  const project = page
    .locator('[data-testid^="aps-project-list-row-"]')
    .first();
  if ((await project.count()) === 0) {
    test.skip(true, "no agentic prompt studio projects in this org");
  }
  await project.click();
  return project;
}

test.describe("agentic prompt studio", () => {
  test("the listing loads and offers project creation", async ({
    page,
    app,
  }) => {
    await app.goto("agentic-prompt-studio/projects");

    await expect(
      page.getByRole("button", { name: /New Project/i }).first(),
      "no way to create a project",
    ).toBeVisible({ timeout: 20000 });
  });

  /*
   * The regression test for the #130 crash. Asserting the error boundary is
   * ABSENT as well as that the surface rendered: an undefined component swaps
   * the whole route for that boundary, so its presence is the precise symptom.
   */
  test("a project opens on its authoring surface", async ({ page, app }) => {
    await openFirstProject(page, app);

    await expect(
      page.getByText(/Couldn't load this page/i),
      "project route hit the error boundary",
    ).toHaveCount(0);

    await expect(
      page.getByRole("tab", { name: /^Status$/ }),
      "authoring surface did not render",
    ).toBeVisible({ timeout: 30000 });
  });

  /*
   * The eight tabs are the project's whole surface. Checking they are all
   * present catches a tab whose panel throws — each one lazily renders
   * different components, so a missing shim shows up per-tab, not globally.
   */
  test("every authoring tab is present", async ({ page, app }) => {
    await openFirstProject(page, app);
    await expect(page.getByRole("tab", { name: /^Status$/ })).toBeVisible({
      timeout: 30000,
    });

    for (const name of [
      "Status",
      "Schema",
      "Extraction Prompt",
      "Verified Data",
      "Extracted Data",
      "Analytics",
      "Mismatch Matrix",
      "Settings",
    ]) {
      await expect(
        page.getByRole("tab", { name, exact: true }),
        `${name} tab missing`,
      ).toBeVisible();
    }
  });

  /*
   * Switching tabs is where a per-tab crash surfaces. Schema and Extraction
   * Prompt are the two authoring tabs; both were verified against the
   * reference to expose these controls.
   */
  test("the Schema and Extraction Prompt tabs render their controls", async ({
    page,
    app,
  }) => {
    await openFirstProject(page, app);
    await expect(page.getByRole("tab", { name: /^Status$/ })).toBeVisible({
      timeout: 30000,
    });

    await page.getByRole("tab", { name: "Schema", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /Generate Schema/i }).first(),
    ).toBeVisible({ timeout: 20000 });

    await page
      .getByRole("tab", { name: "Extraction Prompt", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: /Regenerate/i }).first(),
    ).toBeVisible({ timeout: 20000 });
  });
});
