import { describe, expect, it, vi } from "vitest";
import {
  buildLiveRegistry,
  PREVIEW_STORAGE_KEY,
  parseDistribution,
  readPreviewPages,
} from "./live";

// A declared but unregistered cloud-only page, beside the real demo pages.
vi.mock("./entries", async (importOriginal) => {
  const real = await importOriginal<typeof import("./entries")>();
  return {
    ...real,
    PAGES: [
      {
        page: "UN05",
        v1Routes: ["/:orgName/flows"],
        replaces: ["/:orgName/workflows"],
        toV0: { "/:orgName/flows": "/:orgName/workflows" },
        toV1: { "/:orgName/workflows": "/:orgName/flows" },
        toggle: false,
        distributions: ["cloud"],
        registeredBy: "P3-T01",
      },
    ],
    REGISTERED_PAGES: [],
  };
});

const storageWith = (value: string | null) => ({ getItem: () => value });
const livePages = (options: Parameters<typeof buildLiveRegistry>[0]) =>
  buildLiveRegistry(options).entries.map((e) => e.page);

describe("parseDistribution", () => {
  it("defaults to OSS and accepts any case", () => {
    expect(parseDistribution(undefined)).toBe("oss");
    expect(parseDistribution("")).toBe("oss");
    expect(parseDistribution(" Cloud ")).toBe("cloud");
    expect(parseDistribution("onprem")).toBe("onprem");
  });
  it("is null for an unknown value (vite.config.js fails the build on it)", () => {
    expect(parseDistribution("saas")).toBeNull();
  });
});

describe("readPreviewPages", () => {
  it("reads a JSON array of valid page keys", () => {
    expect(
      readPreviewPages(storageWith('["UN05", 3, "LW02", "UN5", "x"]')),
    ).toEqual(["UN05", "LW02"]);
  });
  it("treats missing, malformed or unreadable storage as no preview", () => {
    expect(readPreviewPages(null)).toEqual([]);
    expect(readPreviewPages(storageWith(null))).toEqual([]);
    expect(readPreviewPages(storageWith("{"))).toEqual([]);
    expect(readPreviewPages(storageWith('{"UN05":1}'))).toEqual([]);
    expect(
      readPreviewPages({
        getItem: () => {
          throw new Error("denied");
        },
      }),
    ).toEqual([]);
  });
  it("uses its own key", () => {
    expect(PREVIEW_STORAGE_KEY).toBe("unstract.v1.preview");
  });
});

describe("buildLiveRegistry", () => {
  const preview = storageWith('["UN05"]');

  it("a declared page stays v0 until registered", () => {
    expect(
      livePages({ devRoutes: false, distribution: "cloud", storage: null }),
    ).toEqual([]);
  });

  it("a release build ignores the preview override and has no demo pages", () => {
    const r = buildLiveRegistry({
      devRoutes: false,
      distribution: "cloud",
      storage: preview,
    });
    expect(r.entries).toEqual([]);
    expect(r.pages.map((p) => p.page)).toEqual(["UN05"]);
  });

  it("with dev routes, the demo pages and previewed pages are live", () => {
    expect(
      livePages({ devRoutes: true, distribution: "cloud", storage: preview }),
    ).toEqual(["UN05", "DEMO-PAGE", "DEMO-REVIEW"]);
  });

  it("drops pages the build's distribution lacks, previewed or not", () => {
    expect(
      livePages({ devRoutes: true, distribution: "oss", storage: preview }),
    ).toEqual(["DEMO-PAGE", "DEMO-REVIEW"]);
  });
});
