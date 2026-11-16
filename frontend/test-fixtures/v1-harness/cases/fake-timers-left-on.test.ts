import { expect, it, vi } from "vitest";

// Known good: a test that leaves fake timers on must not hang the harness.
it("leaves fake timers on", () => {
  vi.useFakeTimers();
  expect(vi.isFakeTimers()).toBe(true);
});

it("runs on real timers afterwards", () => {
  expect(vi.isFakeTimers()).toBe(false);
});
