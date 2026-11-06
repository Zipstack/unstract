/** Self-test: the accessibility helper passes clean pages and fails dirty ones. */

import { DIST, expect, test } from "../../fixtures/index.ts";
import { A11yViolationError } from "../../helpers/a11y.ts";
import { expectAccessible } from "../../helpers/index.ts";

const CLEAN = `<!doctype html><html lang="en"><head><title>clean</title></head>
<body><main><h1>Clean</h1><button type="button">Save</button></main></body></html>`;

// An image with no alt and a nameless button: both `critical` in axe.
const DIRTY = `<!doctype html><html lang="en"><head><title>dirty</title></head>
<body><main><h1>Dirty</h1><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
<button type="button"></button></main></body></html>`;

const LOW_CONTRAST = `<!doctype html><html lang="en"><head><title>contrast</title></head>
<body><main><h1>Contrast</h1><p style="color:#bbbbbb;background:#ffffff">Faint text</p></main></body></html>`;

test.describe("harness: accessibility scan", { tag: DIST.all }, () => {
  test("a clean page passes", async ({ page }) => {
    await page.setContent(CLEAN);
    await expect(expectAccessible(page)).resolves.toBeUndefined();
  });

  test("violations at or above the level fail with their rule ids", async ({
    page,
  }) => {
    await page.setContent(DIRTY);
    const error = await expectAccessible(page).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(A11yViolationError);
    expect(String(error)).toContain("image-alt");
    expect(String(error)).toContain("button-name");
  });

  test("violations below the level pass, at the level fail", async ({
    page,
  }) => {
    // Low-contrast text: `color-contrast` is a `serious` violation.
    await page.setContent(LOW_CONTRAST);
    await expectAccessible(page, { minImpact: "critical" });
    const error = await expectAccessible(page, { minImpact: "serious" }).catch(
      (e: unknown) => e,
    );
    expect(String(error)).toContain("color-contrast");
  });

  test("report mode annotates instead of failing", async ({ page }) => {
    await page.setContent(DIRTY);
    await expectAccessible(page, { mode: "report" });
    expect(
      test.info().annotations.some((a) => a.type === "a11y (report only)"),
    ).toBe(true);
  });

  test("a disabled rule and an excluded region are honoured", async ({
    page,
  }) => {
    await page.setContent(DIRTY);
    await expect(
      expectAccessible(page, {
        disableRules: ["image-alt"],
        exclude: ["button"],
      }),
    ).resolves.toBeUndefined();
  });
});
