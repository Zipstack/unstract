/**
 * P1-T21 document viewer (UN-4390's acceptance checks, task UN-4645), on the
 * viewer's development-only gallery (`/:orgName/v1-demo-viewer`, registered
 * in the E2E image like the other demo pages). The gallery builds its PDFs in
 * the browser, so these need no fixture files and no seeded data.
 *
 *   - A 200-page PDF opens and scrolls smoothly: every page gets a figure,
 *     only the pages near the view get a canvas, the last page paints at the
 *     end, and frames stay short while it scrolls.
 *   - Highlights land on the right region at 50, 100 and 200% zoom: each
 *     target highlight sits on a mark drawn at the same fractions of the page,
 *     checked by geometry and by the colour the page's canvas shows under it.
 */

import {
  GALLERY_IDS,
  LONG_PDF_PAGES,
  TARGETS,
  VIEWER_GALLERY_ROUTE,
  VIEWER_GALLERY_TEST_ID_PREFIX,
} from "../contract/viewer-gallery.ts";
import { DIST, expect, test } from "../fixtures/index.ts";
import { expectAccessible } from "../helpers/index.ts";
import {
  expectOnTarget,
  pageList,
  percentile,
  probeTarget,
  renderedPage,
  scrollThrough,
  setZoom,
} from "../support/viewer.ts";

/*
 * "Smoothly", as numbers: the median frame keeps 30 fps (two 60 Hz frames)
 * and 95% of frames stay under four, on software-rendered headless Chromium.
 * Measured locally (UN-4645): 786 frames, median 16.7 ms, p95 33.4 ms, at
 * most 6 canvases, so CI has twice the headroom. A page only renders near the
 * view (the visible pages plus PAGE_OVERSCAN, 2, on each side), so a dozen
 * canvases already means windowing is off; without it there would be 200.
 */
const MEDIAN_FRAME_MS = 34;
const P95_FRAME_MS = 67;
const MAX_CANVASES = 12;

test.describe("P1-T21 document viewer", { tag: DIST.all }, () => {
  test.beforeEach(async ({ page, app }) => {
    await app.goto(VIEWER_GALLERY_ROUTE);
    await expect(page.getByTestId("v1-demo-viewer")).toBeVisible();
  });

  test("a 200-page PDF opens and scrolls smoothly", async ({ page }) => {
    const section = page.getByTestId(
      `${VIEWER_GALLERY_TEST_ID_PREFIX}${GALLERY_IDS.long}`,
    );
    await section.scrollIntoViewIfNeeded();
    await expect(section.getByText(`/ ${LONG_PDF_PAGES}`)).toBeVisible();
    await expect(renderedPage(section, 0)).toBeVisible();

    const run = await scrollThrough(pageList(section));
    test.info().annotations.push({
      type: "scroll",
      description: `${run.frames.length} frames, median ${percentile(run.frames, 0.5).toFixed(1)} ms, p95 ${percentile(run.frames, 0.95).toFixed(1)} ms, max ${Math.max(...run.frames).toFixed(1)} ms, at most ${run.maxCanvases} canvases`,
    });

    expect(run.figures).toBe(LONG_PDF_PAGES);
    expect(run.maxCanvases).toBeLessThanOrEqual(MAX_CANVASES);
    expect(percentile(run.frames, 0.5)).toBeLessThanOrEqual(MEDIAN_FRAME_MS);
    expect(percentile(run.frames, 0.95)).toBeLessThanOrEqual(P95_FRAME_MS);

    await expect(renderedPage(section, LONG_PDF_PAGES - 1)).toBeVisible();
    await expect(section.getByRole("textbox", { name: "Page" })).toHaveValue(
      String(LONG_PDF_PAGES),
    );
  });

  for (const zoom of ["50%", "100%", "200%"]) {
    test(`highlights land on their marks at ${zoom}`, async ({ page }) => {
      const section = page.getByTestId(
        `${VIEWER_GALLERY_TEST_ID_PREFIX}${GALLERY_IDS.targets}`,
      );
      await section.scrollIntoViewIfNeeded();
      await setZoom(section, zoom);
      await expect(renderedPage(section, 0)).toBeVisible();

      for (const target of TARGETS) {
        await test.step(target.id, async () => {
          const highlight = section.locator(
            `[data-highlight-id="${target.id}"]`,
          );
          await highlight.scrollIntoViewIfNeeded();
          // The canvas repaints after a zoom: retry until it holds the mark,
          // and report the last miss if it never does.
          await expect(async () => {
            expectOnTarget(await probeTarget(highlight), target);
          }).toPass();
        });
      }
    });
  }

  test("the gallery is accessible", async ({ page }) => {
    await expect(
      renderedPage(
        page.getByTestId(
          `${VIEWER_GALLERY_TEST_ID_PREFIX}${GALLERY_IDS.targets}`,
        ),
        0,
      ),
    ).toBeVisible();
    await expectAccessible(page, { label: "viewer-gallery" });
  });
});
