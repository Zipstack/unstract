import {
  expect,
  expectNoHorizontalOverflow,
  expectSharedBaseline,
  test,
} from "./fixtures.js";

/**
 * Prompt Studio: listing, project (Document Parser), and Output Analyzer.
 *
 * The densest cluster of migration regressions. Everything asserted here was
 * found by eye in a browser during the migration and is unobservable in jsdom.
 */

/** Open the first Prompt Studio project, or skip when the org has none. */
async function openFirstProject(page, app) {
  await app.goto("tools");
  const card = page
    .locator("[class*='list-item'], .ant-list-item, [class*='tool-card']")
    .first();
  if ((await card.count()) === 0) {
    test.skip(true, "no prompt studio projects in this org");
  }
  await card.click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await expect(page.getByText("Document Parser").first()).toBeVisible({
    timeout: 15000,
  });
}

test.describe("prompt studio", () => {
  test("the listing renders without horizontal overflow", async ({
    page,
    app,
  }) => {
    await app.goto("tools");
    await expectNoHorizontalOverflow(page, "prompt studio listing");
  });

  /*
   * The doc-manager toolbar sets `align-items: center`, but `.ant-tabs` is a
   * block wrapping the nav AND its content panel — so the 23.6px nav stayed
   * pinned to the top of a 31.6px box and the view tabs sat 5.6px above the
   * file name. The reference measures 0.8px.
   */
  test("the document toolbar shares one baseline", async ({ page, app }) => {
    await openFirstProject(page, app);
    const toolbar = page.locator(".doc-manager-header");
    if ((await toolbar.count()) === 0) {
      test.skip(true, "doc-manager toolbar not rendered");
    }
    await expectSharedBaseline(
      page,
      ".doc-manager-header [role=tab], .doc-manager-header button",
      3,
    );
  });

  /*
   * `size="small"` was not destructured by the TextArea shim, so it rode
   * `...props` onto the DOM and the field kept shadcn's `min-h-[60px]` — every
   * prompt measured 60px against the reference's 32px.
   */
  test("prompt fields are not inflated by a stray min-height", async ({
    page,
    app,
  }) => {
    await openFirstProject(page, app);
    const ta = page.locator("textarea").first();
    if ((await ta.count()) === 0) {
      test.skip(true, "no prompt fields rendered");
    }
    const height = await ta.evaluate((el) => el.getBoundingClientRect().height);
    // A single-line prompt should be nowhere near the 60px floor.
    expect(height, "prompt textarea is taller than antd's").toBeLessThan(50);
  });

  /*
   * A stray `size` attribute is the tell for the whole silent-prop-drop class:
   * `<textarea>` has no `size`, so its presence means the shim forwarded a prop
   * it should have consumed.
   */
  test("no antd-only props leak onto prompt fields", async ({ page, app }) => {
    await openFirstProject(page, app);
    const ta = page.locator("textarea").first();
    if ((await ta.count()) === 0) {
      test.skip(true, "no prompt fields rendered");
    }
    await expect(ta).not.toHaveAttribute("size", /.*/);
  });

  /*
   * The Output Analyzer's profile tabs read `c.props.key`, which React never
   * populates — so nothing matched `activeKey`, the tab rendered permanently
   * inactive with its panel `hidden`, and onChange leaked the ".1:$<uuid>" key
   * into an API call as a profile id (a 500).
   */
  test("the output analyzer activates its profile tab", async ({
    page,
    app,
  }) => {
    await openFirstProject(page, app);

    const failures = [];
    page.on("response", (r) => {
      if (r.status() >= 500) failures.push(`${r.status()} ${r.url()}`);
    });

    const analyzer = page.locator("button:has(svg.lucide-chart-column)").first();
    if ((await analyzer.count()) === 0) {
      test.skip(true, "output analyzer entry point not found");
    }
    await analyzer.click();
    await page.waitForLoadState("networkidle").catch(() => {});

    const tab = page.getByRole("tab").first();
    if ((await tab.count()) === 0) {
      test.skip(true, "no profile tabs rendered");
    }
    // Exactly one tab selected, and its panel visible — "both selected at once"
    // was the reported symptom of the key mismatch.
    await expect(page.getByRole("tab", { selected: true })).toHaveCount(1);
    expect(failures, "output analyzer produced 5xx responses").toEqual([]);
  });
});
