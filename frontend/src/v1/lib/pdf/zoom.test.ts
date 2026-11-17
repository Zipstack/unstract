import { describe, expect, it } from "vitest";
import {
  clampZoom,
  fitZoom,
  formatZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  zoomIn,
  zoomOut,
} from "./zoom";

describe("zoomIn / zoomOut", () => {
  it("steps through the levels", () => {
    expect(zoomIn(1)).toBe(1.25);
    expect(zoomOut(1)).toBe(0.75);
  });

  it("goes to the nearest level from a fitted zoom between levels", () => {
    expect(zoomIn(1.1)).toBe(1.25);
    expect(zoomOut(1.1)).toBe(1);
    expect(zoomIn(0.9999)).toBe(1.25);
  });

  it("stops at the ends", () => {
    expect(zoomIn(MAX_ZOOM)).toBe(MAX_ZOOM);
    expect(zoomOut(MIN_ZOOM)).toBe(MIN_ZOOM);
  });
});

describe("fitZoom", () => {
  const letter = { width: 612, height: 792 };

  it("fits the page width inside the gutter", () => {
    // 612 pt at 96/72 is 816 CSS px.
    expect(fitZoom(letter, 816 + 32, null, 32)).toBeCloseTo(1);
    expect(fitZoom(letter, 408 + 32, null, 32)).toBeCloseTo(0.5);
  });

  it("fits the whole page, limited by the tighter side", () => {
    expect(fitZoom(letter, 2000, 1056 + 32, 32)).toBeCloseTo(1);
  });

  it("stays within the zoom range", () => {
    expect(fitZoom(letter, 10, null, 32)).toBe(MIN_ZOOM);
    expect(fitZoom(letter, 100_000, null, 32)).toBe(MAX_ZOOM);
  });
});

it("clamps and formats", () => {
  expect(clampZoom(10)).toBe(MAX_ZOOM);
  expect(clampZoom(Number.NaN)).toBe(1);
  expect(formatZoom(1.25)).toBe("125%");
  expect(formatZoom(0.333)).toBe("33%");
});
