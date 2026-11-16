import { PAGE_COMPONENTS } from "@v1/app/pages";
import { describe, expect, it } from "vitest";
import { DEMO_PAGES, PAGES, REGISTERED_PAGES } from "./entries";
import { patternProblem, patternsOverlap } from "./patterns";
import type { RegistryEntry } from "./types";
import { registryProblems } from "./validate";

describe("the app's registry", () => {
  const declared = [...PAGES, ...DEMO_PAGES];

  it("is valid", () => {
    expect(registryProblems(declared)).toEqual([]);
  });

  it("registers only declared pages", () => {
    const keys = PAGES.map((p) => p.page);
    expect(REGISTERED_PAGES.filter((k) => !keys.includes(k))).toEqual([]);
  });

  it("has a component for every declared page", () => {
    expect(
      declared.filter((p) => !PAGE_COMPONENTS[p.page]).map((p) => p.page),
    ).toEqual([]);
  });
});

const base: RegistryEntry = {
  page: "UN05",
  v1Routes: ["/:orgName/workflows"],
  replaces: ["/:orgName/old-workflows"],
  toV0: { "/:orgName/workflows": "/:orgName/old-workflows" },
  toV1: { "/:orgName/old-workflows": "/:orgName/workflows" },
  toggle: false,
  distributions: ["oss"],
  registeredBy: "P3-T01",
};

/** An entry with only v1 routes, each mapped back to one v0 route. */
function v1Only(
  page: RegistryEntry["page"],
  v1Routes: string[],
): RegistryEntry {
  return {
    ...base,
    page,
    v1Routes,
    replaces: ["/:orgName/old-workflows"],
    toV0: Object.fromEntries(
      v1Routes.map((r) => [r, "/:orgName/old-workflows"]),
    ),
    toV1: { "/:orgName/old-workflows": v1Routes[0] ?? "" },
  };
}

const problemsOf = (...entries: RegistryEntry[]) => registryProblems(entries);

describe("registryProblems", () => {
  it("accepts a well-formed entry", () => {
    expect(problemsOf(base)).toEqual([]);
  });

  it("rejects the toggle on any page but Human Review (D14)", () => {
    expect(problemsOf({ ...base, toggle: true })).toEqual([
      "UN05: only Human Review (UN11) may honour the old-version preference (D14)",
    ]);
    expect(problemsOf({ ...base, page: "UN11", toggle: true })).toEqual([]);
  });

  it("requires every v1 route to map back to v0, on every page", () => {
    for (const page of ["UN05", "UN11"] as const) {
      expect(
        problemsOf({ ...base, page, toggle: page === "UN11", toV0: {} }),
      ).toEqual([
        `${page}: v1 route /:orgName/workflows has no v0 route to map back to`,
      ]);
    }
  });

  it("requires every replaced v0 route to redirect somewhere", () => {
    expect(problemsOf({ ...base, toV1: {} })).toEqual([
      "UN05: v0 route /:orgName/old-workflows has no v1 route to redirect to",
    ]);
  });

  it("rejects mappings to routes the page does not own, or needing params the source lacks", () => {
    expect(
      problemsOf({
        ...base,
        toV1: { "/:orgName/old-workflows": "/:orgName/x" },
      }),
    ).toEqual([
      "UN05: toV1[/:orgName/old-workflows] -> /:orgName/x is not one of its routes",
    ]);
    expect(
      problemsOf({
        ...base,
        v1Routes: ["/:orgName/workflows/:id"],
        toV0: { "/:orgName/workflows/:id": "/:orgName/old-workflows" },
        toV1: { "/:orgName/old-workflows": "/:orgName/workflows/:id" },
      }),
    ).toEqual([
      "UN05: toV1[/:orgName/old-workflows] -> /:orgName/workflows/:id needs params /:orgName/old-workflows lacks: id",
    ]);
  });

  it("rejects a v1 and a v0 route of the same page that match the same URL", () => {
    // v0 `/hr` outranks the v1 splat `/hr/*` for `/org/hr`: an endless redirect.
    expect(
      problemsOf({
        ...base,
        v1Routes: ["/:orgName/hr/*"],
        replaces: ["/:orgName/hr"],
        toV0: { "/:orgName/hr/*": "/:orgName/hr" },
        toV1: { "/:orgName/hr": "/:orgName/hr/*" },
      }),
    ).toEqual(["UN05: v1 route /:orgName/hr/* overlaps v0 route /:orgName/hr"]);
    // The same shape in Human Review's old-version mode.
    expect(
      problemsOf({
        ...base,
        page: "UN11",
        toggle: true,
        v1Routes: ["/:orgName/review"],
        replaces: ["/:orgName/review/*"],
        toV0: { "/:orgName/review": "/:orgName/review/*" },
        toV1: { "/:orgName/review/*": "/:orgName/review" },
      }),
    ).toEqual([
      "UN11: v1 route /:orgName/review overlaps v0 route /:orgName/review/*",
    ]);
    // A param equal to a static segment: `/old/settings` would redirect to
    // `/new/settings`, which the v0 route takes, and on to `/settings`.
    expect(
      problemsOf({
        ...base,
        v1Routes: ["/new/:id", "/settings"],
        replaces: ["/old/:id", "/new/settings"],
        toV0: { "/new/:id": "/old/:id", "/settings": "/new/settings" },
        toV1: { "/old/:id": "/new/:id", "/new/settings": "/settings" },
      }),
    ).toEqual(["UN05: v1 route /new/:id overlaps v0 route /new/settings"]);
  });

  it("accepts a route both versions share (same-URL takeover)", () => {
    expect(
      problemsOf({
        ...base,
        v1Routes: ["/:orgName/workflows"],
        replaces: ["/:orgName/workflows"],
        toV0: { "/:orgName/workflows": "/:orgName/workflows" },
        toV1: { "/:orgName/workflows": "/:orgName/workflows" },
      }),
    ).toEqual([]);
  });

  it("rejects overlapping patterns across pages, but not shared prefixes", () => {
    expect(problemsOf(base, v1Only("UN10", ["/:orgName/workflows/*"]))).toEqual(
      expect.arrayContaining([
        "UN05 /:orgName/workflows overlaps UN10 /:orgName/workflows/*",
      ]),
    );
    expect(
      problemsOf(base, {
        ...v1Only("UN10", ["/:orgName/workflows/logs"]),
        replaces: ["/:orgName/old-logs"],
        toV0: { "/:orgName/workflows/logs": "/:orgName/old-logs" },
        toV1: { "/:orgName/old-logs": "/:orgName/workflows/logs" },
      }),
    ).toEqual([]);
  });

  it("rejects malformed page keys", () => {
    for (const page of ["UN5", "UN21", "UNKNOWN", "LW08", "DEMO-"] as const) {
      expect(problemsOf({ ...base, page })).toEqual([
        `${page}: not a page key (UN01–UN20, LW01–LW07 or DEMO-…)`,
      ]);
    }
  });

  it("rejects duplicates, empty routes or distributions, and malformed patterns", () => {
    expect(problemsOf(base, base)).toContain("UN05: declared twice");
    expect(
      problemsOf({
        ...base,
        v1Routes: [],
        replaces: [],
        toV0: {},
        toV1: {},
        distributions: [],
      }),
    ).toEqual(["UN05: has no v1 routes", "UN05: ships in no distribution"]);
    expect(
      problemsOf(v1Only("UN05", ["workflows", "/:orgName/:id?", "/a/*/b"])),
    ).toEqual(
      expect.arrayContaining([
        "UN05: route workflows must start with /",
        "UN05: route /:orgName/:id? segment ':id?' is not a static name, :param or a final *",
        "UN05: route /a/*/b * is allowed only as the last segment",
      ]),
    );
  });
});

describe("patterns", () => {
  it.each([
    ["/:o/a", "/:o/a", true],
    ["/:o/a", "/x/a", true],
    ["/:o/a", "/:o/b", false],
    ["/:o/a", "/:o/a/b", false],
    ["/:o/a/*", "/:o/a", true],
    ["/:o/a/*", "/:o/a/b/c", true],
    ["/:o/a/*", "/:o/b/c", false],
    ["/:o/A", "/:o/a", true],
  ])("%s and %s overlap: %s", (a, b, expected) => {
    expect(patternsOverlap(a, b)).toBe(expected);
    expect(patternsOverlap(b, a)).toBe(expected);
  });

  it("accepts static, param and final-splat segments", () => {
    expect(patternProblem("/llm-whisperer/:orgName/api-keys/*")).toBeNull();
  });
});
