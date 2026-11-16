import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useDevicePixelRatio } from "./useDevicePixelRatio";

const listeners = new Map<string, () => void>();

afterEach(() => {
  vi.unstubAllGlobals();
  listeners.clear();
  window.devicePixelRatio = 1;
});

it("follows the ratio when the window moves to another screen", () => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    addEventListener: (_: string, listener: () => void) =>
      listeners.set(query, listener),
    removeEventListener: () => listeners.delete(query),
  }));
  window.devicePixelRatio = 1;
  const { result } = renderHook(() => useDevicePixelRatio());
  expect(result.current).toBe(1);
  expect([...listeners.keys()]).toEqual(["(resolution: 1dppx)"]);

  window.devicePixelRatio = 2;
  act(() => listeners.get("(resolution: 1dppx)")?.());
  expect(result.current).toBe(2);
  expect([...listeners.keys()]).toEqual(["(resolution: 2dppx)"]);
});
