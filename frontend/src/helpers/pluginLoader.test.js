import { afterEach, describe, expect, it, vi } from "vitest";

import { isPluginAbsent, loadPlugin } from "./pluginLoader.js";

const absent = () => Promise.reject(new Error("Optional plugin not available"));

describe("loadPlugin", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves to what the importer returns", async () => {
    const Comp = () => null;
    await expect(loadPlugin(() => Promise.resolve(Comp))).resolves.toBe(Comp);
  });

  it("keeps falsy values that are not null/undefined", async () => {
    await expect(loadPlugin(() => Promise.resolve(false), true)).resolves.toBe(
      false,
    );
  });

  it("falls back silently when the plugin is absent", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const fallback = () => null;

    await expect(loadPlugin(absent, fallback)).resolves.toBe(fallback);
    expect(error).not.toHaveBeenCalled();
  });

  it("defaults the fallback to null", async () => {
    await expect(loadPlugin(absent)).resolves.toBeNull();
  });

  it("falls back when the picked export is missing", async () => {
    await expect(
      loadPlugin(() => Promise.resolve({}).then((m) => m.Missing), "fb"),
    ).resolves.toBe("fb");
  });

  it("logs a broken plugin and still falls back", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const boom = new Error("boom at module evaluation");

    await expect(loadPlugin(() => Promise.reject(boom), "fb")).resolves.toBe(
      "fb",
    );
    expect(error).toHaveBeenCalledWith(
      expect.stringContaining("[plugin]"),
      boom,
    );
  });

  it("logs a chunk that failed to fetch instead of treating it as absent", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const chunk = new TypeError(
      "Failed to fetch dynamically imported module: /assets/x-abc.js",
    );

    await expect(loadPlugin(() => Promise.reject(chunk))).resolves.toBeNull();
    expect(error).toHaveBeenCalledOnce();
  });

  it("catches an importer that throws synchronously", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    await expect(
      loadPlugin(() => {
        throw new Error("sync");
      }, "fb"),
    ).resolves.toBe("fb");
  });
});

describe("isPluginAbsent", () => {
  it.each([
    [new Error("Optional plugin not available"), true],
    [Object.assign(new Error("x"), { code: "MODULE_NOT_FOUND" }), true],
    [new Error("Cannot find module '../plugins/x'"), true],
    [
      new TypeError("Failed to fetch dynamically imported module: /a.js"),
      false,
    ],
    [new Error("boom"), false],
    [undefined, false],
  ])("classifies %s as absent=%s", (err, expected) => {
    expect(isPluginAbsent(err)).toBe(expected);
  });
});
