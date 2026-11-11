import { describe, expect, it, vi } from "vitest";
import { isChunkLoadError, reloadOnce } from "./chunkReload";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
  };
}

describe("isChunkLoadError", () => {
  it.each([
    new TypeError("Failed to fetch dynamically imported module: /a.js"),
    new TypeError("error loading dynamically imported module"),
    new TypeError("Importing a module script failed."),
    Object.assign(new Error("x"), { name: "ChunkLoadError" }),
  ])("matches %s", (error) => {
    expect(isChunkLoadError(error)).toBe(true);
  });

  it("does not match render errors or non-errors", () => {
    expect(isChunkLoadError(new Error("Cannot read properties of null"))).toBe(
      false,
    );
    expect(
      isChunkLoadError("Failed to fetch dynamically imported module"),
    ).toBe(false);
  });
});

describe("reloadOnce", () => {
  it("reloads once, then not again within ten seconds, then again after", () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    expect(reloadOnce(storage, reload, 100_000)).toBe(true);
    expect(reloadOnce(storage, reload, 105_000)).toBe(false);
    expect(reloadOnce(storage, reload, 110_000)).toBe(false); // exactly ten seconds
    expect(reloadOnce(storage, reload, 110_001)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("never reloads without usable session storage", () => {
    const reload = vi.fn();
    expect(reloadOnce(null, reload)).toBe(false);
    const refusing = {
      getItem: () => null,
      setItem: () => {
        throw new Error("denied");
      },
    };
    expect(reloadOnce(refusing, reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});
