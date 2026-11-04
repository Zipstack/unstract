import { describe, expect, it } from "vitest";
import { DEMO_PAGES } from "./entries";
import {
  buildLiveRegistry,
  PREVIEW_STORAGE_KEY,
  parseDistribution,
  readPreviewPages,
} from "./live";

const storageWith = (value: string | null) => ({ getItem: () => value });

describe("parseDistribution", () => {
  it("defaults to OSS and accepts any case", () => {
    expect(parseDistribution(undefined)).toBe("oss");
    expect(parseDistribution("")).toBe("oss");
    expect(parseDistribution(" Cloud ")).toBe("cloud");
    expect(parseDistribution("onprem")).toBe("onprem");
  });
  it("fails the build on an unknown value", () => {
    expect(() => parseDistribution("saas")).toThrow(
      "VITE_UNSTRACT_DISTRIBUTION=saas",
    );
  });
});

describe("readPreviewPages", () => {
  it("reads a JSON array of page keys", () => {
    expect(readPreviewPages(storageWith('["UN05", 3, "LW02"]'))).toEqual([
      "UN05",
      "LW02",
    ]);
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
  it("without dev routes: no demo pages, and the preview override is ignored", () => {
    const r = buildLiveRegistry({
      devRoutes: false,
      distribution: "oss",
      storage: storageWith('["DEMO-PAGE"]'),
    });
    expect(r.pages.some((p) => p.page.startsWith("DEMO-"))).toBe(false);
    expect(r.entries).toEqual([]);
  });

  it("with dev routes: the demo pages are declared and live", () => {
    const r = buildLiveRegistry({
      devRoutes: true,
      distribution: "oss",
      storage: null,
    });
    expect(r.entries.map((e) => e.page)).toEqual(DEMO_PAGES.map((p) => p.page));
  });
});
