import { afterEach, expect, it, vi } from "vitest";
import { resetScrollbarWidth, scrollbarWidth } from "./scrollbar";

afterEach(() => {
  resetScrollbarWidth();
  vi.restoreAllMocks();
});

function withScrollbar(width: number) {
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(100);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(
    100 - width,
  );
}

it("measures a classic scrollbar, and removes its probe", () => {
  withScrollbar(17);
  const before = document.body.childElementCount;
  expect(scrollbarWidth()).toBe(17);
  expect(document.body.childElementCount).toBe(before);
});

it("is 0 with overlay scrollbars", () => {
  withScrollbar(0);
  expect(scrollbarWidth()).toBe(0);
});

it("measures once", () => {
  withScrollbar(15);
  const append = vi.spyOn(document.body, "appendChild");
  scrollbarWidth();
  scrollbarWidth();
  expect(append).toHaveBeenCalledTimes(1);
});
