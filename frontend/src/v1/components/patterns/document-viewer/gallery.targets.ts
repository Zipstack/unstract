/*
 * What the document viewer's browser tests (tests/e2e/ui-v1/specs/
 * P1-T21.spec.ts) need to know about its gallery, kept free of imports so the
 * E2E suite can read it without Vite or the `@v1` alias. The gallery builds
 * its PDFs from these values, so the tests and the page cannot drift.
 */

/** The demo page's route segment, under `/:orgName/`. */
export const VIEWER_GALLERY_ROUTE = "v1-demo-viewer";

/** Each gallery entry's section has the test id `<prefix><entry id>`. */
export const VIEWER_GALLERY_TEST_ID_PREFIX = "viewer-gallery-";

/** Pages in the long PDF: UN-4390's "a 200-page PDF opens and scrolls smoothly". */
export const LONG_PDF_PAGES = 200;

/** Fill of the target marks; a highlight placed on a mark must cover this colour. */
export const MARK_RGB = [230, 40, 40] as const;

/** A target: a mark drawn on page 1 and a highlight at the same fractions. */
export interface ViewerTarget {
  id: string;
  /** Fractions of the page box, from the top-left. */
  x: number;
  y: number;
  w: number;
  h: number;
  variant: "line" | "box";
}

/**
 * A wide line near the top, a box in the middle and a small one near the
 * bottom-right corner, where an offset or a scaling error shows most.
 */
export const TARGETS: readonly ViewerTarget[] = [
  { id: "target-line", x: 0.1, y: 0.15, w: 0.8, h: 0.03, variant: "line" },
  { id: "target-box", x: 0.35, y: 0.45, w: 0.3, h: 0.1, variant: "box" },
  { id: "target-corner", x: 0.8, y: 0.88, w: 0.12, h: 0.05, variant: "box" },
];

/** Gallery entry ids the browser tests open. */
export const GALLERY_IDS = {
  long: "pdf-long",
  targets: "pdf-targets",
} as const;
