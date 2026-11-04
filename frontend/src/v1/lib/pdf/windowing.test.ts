import { describe, expect, it } from "vitest";
import {
  CSS_PIXELS_PER_POINT,
  canvasPixelRatio,
  MAX_CANVAS_PIXELS,
  pageCssSize,
  pageWindow,
} from "./windowing";

describe("pageWindow", () => {
  it("adds two pages on each side of the visible ones", () => {
    expect([...pageWindow([10, 11], 200)]).toEqual([8, 9, 10, 11, 12, 13]);
  });

  it("clamps to the first and last page", () => {
    expect([...pageWindow([0], 200)]).toEqual([0, 1, 2]);
    expect([...pageWindow([199], 200)]).toEqual([197, 198, 199]);
    expect([...pageWindow([0], 1)]).toEqual([0]);
  });

  it("covers the gap when visible pages are not contiguous", () => {
    expect([...pageWindow([5, 3], 200, 0)]).toEqual([3, 4, 5]);
  });

  it("renders nothing when nothing is visible, and ignores stale indexes", () => {
    expect(pageWindow([], 200).size).toBe(0);
    expect(pageWindow([250], 200).size).toBe(0);
  });
});

describe("canvasPixelRatio", () => {
  it("uses the screen ratio up to 2", () => {
    expect(canvasPixelRatio(800, 1000, 1)).toBe(1);
    expect(canvasPixelRatio(800, 1000, 1.5)).toBe(1.5);
    expect(canvasPixelRatio(800, 1000, 3)).toBe(2);
  });

  it("falls back to 1 for a missing or broken ratio", () => {
    expect(canvasPixelRatio(800, 1000, 0)).toBe(1);
    expect(canvasPixelRatio(800, 1000, Number.NaN)).toBe(1);
  });

  it("keeps a huge page inside the largest canvas a browser allocates", () => {
    const ratio = canvasPixelRatio(5000, 5000, 2);
    expect(ratio).toBeLessThan(2);
    expect(5000 * ratio * (5000 * ratio)).toBeLessThanOrEqual(
      MAX_CANVAS_PIXELS + 1,
    );
  });
});

describe("pageCssSize", () => {
  it("shows a page at its printed size at 100%", () => {
    expect(pageCssSize({ width: 612, height: 792 }, 1)).toEqual({
      width: 612 * CSS_PIXELS_PER_POINT,
      height: 792 * CSS_PIXELS_PER_POINT,
    });
    expect(pageCssSize({ width: 72, height: 72 }, 2)).toEqual({
      width: 192,
      height: 192,
    });
  });
});
