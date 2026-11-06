/*
 * Zoom levels for the document viewer. Zoom 1 is 100%: a page at its printed
 * size (see CSS_PIXELS_PER_POINT).
 */
import type { PageSize } from "./types";
import { CSS_PIXELS_PER_POINT } from "./windowing";

/** The levels the − and + buttons step through. */
export const ZOOM_STEPS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4] as const;
export const MIN_ZOOM = ZOOM_STEPS[0];
export const MAX_ZOOM = ZOOM_STEPS[ZOOM_STEPS.length - 1];

/** How the zoom is chosen: a fixed level, or fitted to the viewer. */
export type ZoomMode = "custom" | "fit-width" | "fit-page";

// Two steps a hair apart (a fitted 0.9999) should not count as different.
const EPSILON = 1e-3;

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) {
    return 1;
  }
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

/** The next level above the current zoom, which may be between steps. */
export function zoomIn(zoom: number): number {
  return ZOOM_STEPS.find((step) => step > zoom + EPSILON) ?? MAX_ZOOM;
}

/** The next level below the current zoom, which may be between steps. */
export function zoomOut(zoom: number): number {
  for (let index = ZOOM_STEPS.length - 1; index >= 0; index--) {
    const step = ZOOM_STEPS[index];
    if (step !== undefined && step < zoom - EPSILON) {
      return step;
    }
  }
  return MIN_ZOOM;
}

/**
 * The zoom at which a page fills the given width, or the given box when a
 * height is given too. `gutter` is the space kept around the page, in CSS px.
 */
export function fitZoom(
  page: PageSize,
  width: number,
  height: number | null,
  gutter: number,
): number {
  const byWidth = (width - gutter) / (page.width * CSS_PIXELS_PER_POINT);
  if (height === null) {
    return clampZoom(byWidth);
  }
  const byHeight = (height - gutter) / (page.height * CSS_PIXELS_PER_POINT);
  return clampZoom(Math.min(byWidth, byHeight));
}

/** The zoom as the toolbar shows it, e.g. "125%". */
export function formatZoom(zoom: number): string {
  return `${Math.round(zoom * 100)}%`;
}
