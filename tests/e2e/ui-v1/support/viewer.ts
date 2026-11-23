/**
 * Checks on the v1 document viewer, run by specs/P1-T21.spec.ts against its
 * gallery. Each takes the gallery section that holds one viewer, so a check
 * never reaches into another entry.
 */

import { expect, type Locator } from "@playwright/test";
import { MARK_RGB, type ViewerTarget } from "../contract/viewer-gallery.ts";

/** The viewer's scroll region, which holds one figure per page. */
export function pageList(section: Locator): Locator {
  return section.getByRole("region", { name: "Document pages" });
}

/** A 0-based page, once pdf.js has painted it. */
export function renderedPage(section: Locator, index: number): Locator {
  return section.locator(
    `figure[data-page-index="${index}"][data-render-state="rendered"]`,
  );
}

/** Steps the toolbar's − and + until it shows `label`, e.g. "50%". */
export async function setZoom(section: Locator, label: string): Promise<void> {
  const level = section.getByRole("status", { name: "Zoom level" });
  const target = Number.parseInt(label, 10);
  for (let step = 0; step < 12; step++) {
    const current = Number.parseInt((await level.textContent()) ?? "", 10);
    if (current === target) {
      return;
    }
    const button = current > target ? "Zoom out" : "Zoom in";
    await section.getByRole("button", { name: button }).click();
    await expect(level).not.toHaveText(`${current}%`);
  }
  await expect(level).toHaveText(label);
}

export interface ScrollRun {
  /** Time between consecutive animation frames while scrolling, in ms. */
  frames: number[];
  /** The most page canvases alive at any frame. */
  maxCanvases: number;
  /** Pages with a figure in the list. */
  figures: number;
}

/**
 * Scrolls the page list from top to bottom, `step` CSS px per animation
 * frame, as a fast drag of the scrollbar would, and records every frame's
 * duration and how many canvases were alive.
 */
export function scrollThrough(list: Locator, step = 400): Promise<ScrollRun> {
  return list.evaluate(
    (root, { px, MAX_FRAMES, STALL_FRAMES }) =>
      new Promise<ScrollRun>((resolve) => {
        const frames: number[] = [];
        let maxCanvases = 0;
        let last = performance.now();
        let previous = -1;
        let stalled = 0;
        root.scrollTop = 0;
        const tick = (now: number) => {
          frames.push(now - last);
          last = now;
          maxCanvases = Math.max(
            maxCanvases,
            root.querySelectorAll("canvas").length,
          );
          const end = root.scrollHeight - root.clientHeight;
          // A list that stops scrolling ends the run rather than spinning
          // until the test times out, so the page checks report it.
          stalled = root.scrollTop === previous ? stalled + 1 : 0;
          previous = root.scrollTop;
          if (
            root.scrollTop >= end - 1 ||
            stalled > STALL_FRAMES ||
            frames.length > MAX_FRAMES
          ) {
            resolve({
              frames: frames.slice(1),
              maxCanvases,
              figures: root.querySelectorAll("figure[data-page-index]").length,
            });
            return;
          }
          root.scrollTop = Math.min(end, root.scrollTop + px);
          requestAnimationFrame(tick);
        };
        requestAnimationFrame((now) => {
          last = now;
          requestAnimationFrame(tick);
        });
      }),
    { px: step, MAX_FRAMES: 3000, STALL_FRAMES: 30 },
  );
}

/** The value below which `share` of the samples fall, e.g. 0.95. */
export function percentile(values: readonly number[], share: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(
    sorted.length - 1,
    Math.ceil(share * sorted.length) - 1,
  );
  return sorted[Math.max(0, index)] ?? 0;
}

type Rgb = [number, number, number];

export interface TargetProbe {
  /** The highlight's box in fractions of its page box. */
  box: { x: number; y: number; w: number; h: number };
  /** The page's size in CSS px, to turn fractions into pixels. */
  page: { width: number; height: number };
  /**
   * Canvas pixels per CSS px, and what a canvas painted at this zoom has.
   * While a page repaints after a zoom it shows its old bitmap stretched,
   * whose marks still sit at the same fractions; this tells the two apart.
   */
  scale: number;
  expectedScale: number;
  /** Canvas colour at points inside the highlight. */
  inside: Rgb[];
  /** Canvas colour just outside each edge of the highlight. */
  outside: Rgb[];
}

/**
 * Reads where a highlight sits on its page and what the page's canvas shows
 * under it: at its centre and four inner points, and `gap` CSS px beyond the
 * middle of each edge. The canvas holds the PDF alone; highlights are
 * separate elements laid over it, so the colours are the document's.
 */
export function probeTarget(highlight: Locator, gap = 4): Promise<TargetProbe> {
  return highlight.evaluate((element, px) => {
    const figure = element.closest("figure");
    const canvas = figure?.querySelector("canvas");
    const context = canvas?.getContext("2d");
    if (!figure || !canvas || !context) {
      throw new Error("The highlight's page has no painted canvas");
    }
    const page = figure.getBoundingClientRect();
    const own = element.getBoundingClientRect();
    const paint = canvas.getBoundingClientRect();
    const scaleX = canvas.width / paint.width;
    const scaleY = canvas.height / paint.height;
    const at = (x: number, y: number): Rgb => {
      const data = context.getImageData(
        Math.floor((x - paint.left) * scaleX),
        Math.floor((y - paint.top) * scaleY),
        1,
        1,
      ).data;
      return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0];
    };
    const midX = own.left + own.width / 2;
    const midY = own.top + own.height / 2;
    const inner = (share: number, size: number, start: number) =>
      start + share * size;
    return {
      box: {
        x: (own.left - page.left) / page.width,
        y: (own.top - page.top) / page.height,
        w: own.width / page.width,
        h: own.height / page.height,
      },
      page: { width: page.width, height: page.height },
      scale: canvas.width / paint.width,
      // The viewer's cap (MAX_PIXEL_RATIO); these pages stay under the
      // canvas size limit, which would lower it further.
      expectedScale: Math.min(window.devicePixelRatio || 1, 2),
      inside: [
        at(midX, midY),
        at(inner(0.2, own.width, own.left), inner(0.25, own.height, own.top)),
        at(inner(0.8, own.width, own.left), inner(0.25, own.height, own.top)),
        at(inner(0.2, own.width, own.left), inner(0.75, own.height, own.top)),
        at(inner(0.8, own.width, own.left), inner(0.75, own.height, own.top)),
      ],
      outside: [
        at(midX, own.top - px),
        at(midX, own.bottom + px),
        at(own.left - px, midY),
        at(own.right + px, midY),
      ],
    };
  }, gap);
}

function near(
  colour: Rgb,
  expected: readonly number[],
  tolerance = 12,
): boolean {
  return colour.every(
    (channel, index) => Math.abs(channel - (expected[index] ?? 0)) <= tolerance,
  );
}

/**
 * The highlight sits at the target's fractions of its page, to within a CSS
 * pixel, and the page's own mark fills it: the mark's colour at every inner
 * point, and not beyond any edge.
 */
export function expectOnTarget(probe: TargetProbe, target: ViewerTarget): void {
  const { width, height } = probe.page;
  expect(
    Math.abs(probe.scale - probe.expectedScale),
    "the page is painted at this zoom",
  ).toBeLessThanOrEqual(0.02 * probe.expectedScale);
  expect(Math.abs(probe.box.x - target.x) * width).toBeLessThanOrEqual(1);
  expect(Math.abs(probe.box.y - target.y) * height).toBeLessThanOrEqual(1);
  expect(Math.abs(probe.box.w - target.w) * width).toBeLessThanOrEqual(1);
  expect(Math.abs(probe.box.h - target.h) * height).toBeLessThanOrEqual(1);
  for (const colour of probe.inside) {
    expect(near(colour, MARK_RGB), `inside: ${colour}`).toBe(true);
  }
  for (const colour of probe.outside) {
    expect(near(colour, MARK_RGB), `outside: ${colour}`).toBe(false);
  }
}
