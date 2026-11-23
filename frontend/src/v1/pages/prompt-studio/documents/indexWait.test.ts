import { describe, expect, it } from "vitest";
import { isSettled } from "./indexWait";

describe("isSettled", () => {
  const start = { status: "failed", reason: "no text", at: 0 } as const;

  it("waits while nothing has changed", () => {
    expect(
      isSettled(start, { status: "failed", reason: "no text" }, 1000),
    ).toBe(false);
  });

  it("settles when the state or the reason changes", () => {
    expect(isSettled(start, { status: "indexed", reason: null }, 1000)).toBe(
      true,
    );
    expect(
      isSettled(start, { status: "failed", reason: "timeout" }, 1000),
    ).toBe(true);
  });

  it("settles when the document is gone", () => {
    expect(isSettled(start, undefined, 1000)).toBe(true);
  });

  it("gives up waiting after three minutes", () => {
    const current = { status: "failed", reason: "no text" } as const;
    expect(isSettled(start, current, 3 * 60_000 - 1)).toBe(false);
    expect(isSettled(start, current, 3 * 60_000)).toBe(true);
  });
});
