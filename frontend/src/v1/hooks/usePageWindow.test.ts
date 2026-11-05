import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { usePageWindow } from "./usePageWindow";

let report: ((entries: object[]) => void) | null = null;

class FakeIntersectionObserver {
  constructor(callback: (entries: object[]) => void) {
    report = callback;
  }
  observe() {
    // Entries arrive only when a test calls report().
  }
  unobserve() {
    // Nothing to stop.
  }
  disconnect() {
    report = null;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  report = null;
});

it("skips an element without a page index instead of reading it as page 0", () => {
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  const { result } = renderHook(() => usePageWindow(10, 0));
  act(() => result.current.scrollRef(document.createElement("div")));
  const stray = document.createElement("div");
  const page = document.createElement("div");
  page.setAttribute("data-page-index", "4");
  act(() =>
    report?.([
      { target: stray, isIntersecting: true },
      { target: page, isIntersecting: true },
    ]),
  );
  expect([...result.current.visible]).toEqual([4]);
});
