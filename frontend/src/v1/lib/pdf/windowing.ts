/*
 * The arithmetic behind windowed page rendering: which pages get a canvas, and
 * how many device pixels each canvas may use. Kept free of React and the DOM
 * so it can be tested on its own.
 */

/** Pages rendered on each side of the visible ones. */
export const PAGE_OVERSCAN = 2;

/** Higher densities cost memory and render time with no visible gain. */
export const MAX_PIXEL_RATIO = 2;

/**
 * The largest canvas, in pixels, that every target browser will allocate:
 * Safari refuses anything above 16,777,216, and a refused canvas paints
 * nothing at all.
 */
export const MAX_CANVAS_PIXELS = 16_777_216;

/** CSS pixels per PDF point, so 100% zoom shows a page at its printed size. */
export const CSS_PIXELS_PER_POINT = 96 / 72;

/**
 * The 0-based pages to render: the visible ones, plus `overscan` on each side,
 * clamped to the document. Nothing is rendered while nothing is visible, which
 * is the case before the first layout.
 */
export function pageWindow(
  visible: Iterable<number>,
  pageCount: number,
  overscan: number = PAGE_OVERSCAN,
): Set<number> {
  let first = Number.POSITIVE_INFINITY;
  let last = Number.NEGATIVE_INFINITY;
  for (const index of visible) {
    if (index >= 0 && index < pageCount) {
      first = Math.min(first, index);
      last = Math.max(last, index);
    }
  }
  const pages = new Set<number>();
  if (first > last) {
    return pages;
  }
  const from = Math.max(0, first - overscan);
  const to = Math.min(pageCount - 1, last + overscan);
  for (let index = from; index <= to; index++) {
    pages.add(index);
  }
  return pages;
}

/**
 * Device pixels per CSS pixel for a canvas of the given CSS size: the screen's
 * ratio, capped at `MAX_PIXEL_RATIO`, and lowered further if the canvas would
 * otherwise exceed `MAX_CANVAS_PIXELS`.
 */
export function canvasPixelRatio(
  cssWidth: number,
  cssHeight: number,
  devicePixelRatio: number,
): number {
  const screen =
    Number.isFinite(devicePixelRatio) && devicePixelRatio > 0
      ? devicePixelRatio
      : 1;
  const ratio = Math.min(screen, MAX_PIXEL_RATIO);
  const area = cssWidth * cssHeight;
  if (area <= 0) {
    return ratio;
  }
  return Math.min(ratio, Math.sqrt(MAX_CANVAS_PIXELS / area));
}

/** A page's CSS size at a zoom, where zoom 1 is 100%. */
export function pageCssSize(
  size: { width: number; height: number },
  zoom: number,
): { width: number; height: number } {
  const scale = zoom * CSS_PIXELS_PER_POINT;
  return { width: size.width * scale, height: size.height * scale };
}
