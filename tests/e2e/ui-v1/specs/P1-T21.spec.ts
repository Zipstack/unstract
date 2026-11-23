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
 * and 95% of frames stay under 100 ms, the point where a pause shows, on
 * software-rendered headless Chromium. Measured locally (UN-4645), the median
 * is one frame and p95 two; the p95 bound is looser than the median's
 * because CI runs the whole platform on the same machine, and a retry that
 * passes still fails the run (failOnFlakyTests). A page only renders near the
 * view (the visible pages plus PAGE_OVERSCAN, 2, on each side), so a dozen
 * canvases already means windowing is off; without it there would be 200.
 */
const MEDIAN_FRAME_MS = 34;
const P95_FRAME_MS = 100;
const MAX_CANVASES = 12;
/** Too few frames means the list never scrolled, and empty timings pass. */
const MIN_FRAMES = 200;
/**
 * Two speeds. A fast drag moves a page into and out of the window every few
 * frames, so it loads windowing: canvases mounted, painted and dropped.
 * Reading speed is how a person scrolls, each page painting as it arrives.
 */
const DRAG_PX = 400;
const READ_PX = 40;
const READ_PAGES = 10;
/**
 * At reading speed only about one frame in thirty paints a page, too few to
 * move a percentile, so paint cost is checked by counting long frames: a
 * frame of 50 ms or more is a browser "long task". Locally none occur; a
 * 60 ms stall added to each page paint gives one per page. Half the pages is
 * room for the odd stall a busy CI machine adds.
 */
const LONG_FRAME_MS = 50;
const MAX_LONG_READ_FRAMES = READ_PAGES / 2;

test.describe("P1-T21 document viewer", { tag: DIST.all }, () => {
  test.beforeEach(async ({ page, app }) => {
    await app.goto(VIEWER_GALLERY_ROUTE);
    await expect(page.getByTestId("v1-demo-viewer")).toBeVisible();
  });

  test("a 200-page PDF opens and scrolls smoothly", async ({ page }) => {
    // The two scrolls take ~20 s on their own.
    test.setTimeout(120_000);
    const section = page.getByTestId(
      `${VIEWER_GALLERY_TEST_ID_PREFIX}${GALLERY_IDS.long}`,
    );
    await section.scrollIntoViewIfNeeded();
    await expect(section.getByText(`/ ${LONG_PDF_PAGES}`)).toBeVisible();
    await expect(renderedPage(section, 0)).toBeVisible();

    const list = pageList(section);
    const read = await scrollThrough(list, {
      step: READ_PX,
      untilPage: READ_PAGES,
    });
    const drag = await scrollThrough(list, { step: DRAG_PX });
    for (const [name, run] of [
      ["read", read],
      ["drag", drag],
    ] as const) {
      test.info().annotations.push({
        type: `scroll-${name}`,
        description: `${run.frames.length} frames, median ${percentile(run.frames, 0.5).toFixed(1)} ms, p95 ${percentile(run.frames, 0.95).toFixed(1)} ms, max ${Math.max(...run.frames).toFixed(1)} ms, at most ${run.maxCanvases} canvases, ${run.renderedPages} pages painted`,
      });
    }

    expect(drag.figures).toBe(LONG_PDF_PAGES);
    // Every page passed at reading speed painted while the frames were timed.
    expect(read.renderedPages).toBeGreaterThanOrEqual(READ_PAGES);
    expect(
      read.frames.filter((frame) => frame >= LONG_FRAME_MS).length,
    ).toBeLessThanOrEqual(MAX_LONG_READ_FRAMES);
    for (const run of [read, drag]) {
      expect(run.frames.length).toBeGreaterThanOrEqual(MIN_FRAMES);
      expect(run.maxCanvases).toBeLessThanOrEqual(MAX_CANVASES);
      expect(percentile(run.frames, 0.5)).toBeLessThanOrEqual(MEDIAN_FRAME_MS);
      expect(percentile(run.frames, 0.95)).toBeLessThanOrEqual(P95_FRAME_MS);
    }

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
          // and report the last miss if it never does. toPass has no time
          // limit of its own, so without one a miss ends as a test timeout.
          await expect(async () => {
            expectOnTarget(await probeTarget(highlight), target);
          }).toPass({ timeout: 10_000 });
        });
      }
    });
  }

  test("the gallery is accessible", async ({ page }) => {
    // Scan once every PDF entry has settled, not while one still loads.
    const entry = (id: string) =>
      page.getByTestId(`${VIEWER_GALLERY_TEST_ID_PREFIX}${id}`);
    for (const id of [
      "pdf-highlights",
      GALLERY_IDS.long,
      GALLERY_IDS.targets,
    ]) {
      await expect(renderedPage(entry(id), 0)).toBeVisible();
    }
    await expect(
      entry("pdf-unsupported").getByText("This file can't be previewed"),
    ).toBeVisible();
    await expectAccessible(page, { label: "viewer-gallery" });
  });
});
