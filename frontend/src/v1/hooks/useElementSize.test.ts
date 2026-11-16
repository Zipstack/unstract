import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useElementSize } from "./useElementSize";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("measures once where ResizeObserver is missing, rather than throwing", () => {
  vi.stubGlobal("ResizeObserver", undefined);
  const element = document.createElement("div");
  vi.spyOn(element, "clientWidth", "get").mockReturnValue(640);
  vi.spyOn(element, "clientHeight", "get").mockReturnValue(480);
  const { result } = renderHook(() => useElementSize<HTMLDivElement>());
  act(() => result.current[0](element));
  expect(result.current[1]).toEqual({ width: 640, height: 480 });
});

it("follows the element's size with a ResizeObserver", () => {
  let report: ResizeObserverCallback = () => undefined;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: ResizeObserverCallback) {
        report = callback;
      }
      observe() {
        // Sizes arrive only through report().
      }
      disconnect() {
        // Nothing to release.
      }
    },
  );
  const { result } = renderHook(() => useElementSize<HTMLDivElement>());
  act(() => result.current[0](document.createElement("div")));
  expect(result.current[1]).toBeNull();
  act(() =>
    report(
      [{ contentRect: { width: 300, height: 200 } } as ResizeObserverEntry],
      {} as ResizeObserver,
    ),
  );
  expect(result.current[1]).toEqual({ width: 300, height: 200 });
});
