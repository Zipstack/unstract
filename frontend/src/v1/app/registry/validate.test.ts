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
  toV0: {},
  toV1: { "/:orgName/old-workflows": "/:orgName/workflows" },
  toggle: false,
  distributions: ["oss"],
  registeredBy: "P3-T01",
};

const problemsOf = (...entries: RegistryEntry[]) => registryProblems(entries);

describe("registryProblems", () => {
  it("accepts a well-formed entry", () => {
    expect(problemsOf(base)).toEqual([]);
  });

  it("rejects the toggle on any page but Human Review (D14)", () => {
    expect(
      problemsOf({
        ...base,
        toggle: true,
        toV0: { "/:orgName/workflows": "/:orgName/old-workflows" },
      }),
    ).toEqual([
      "UN05: only Human Review (UN11) may honour the old-version preference (D14)",
    ]);
    expect(
      problemsOf({
        ...base,
        page: "UN11",
        toggle: true,
        toV0: { "/:orgName/workflows": "/:orgName/old-workflows" },
      }),
    ).toEqual([]);
  });

  it("requires a toggle page to map every v1 route back to v0", () => {
    expect(problemsOf({ ...base, page: "UN11", toggle: true })).toEqual([
      "UN11: v1 route /:orgName/workflows has no v0 route for old-version mode",
    ]);
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
        toV1: { "/:orgName/old-workflows": "/:orgName/workflows/:id" },
      }),
    ).toEqual([
      "UN05: toV1[/:orgName/old-workflows] -> /:orgName/workflows/:id needs params /:orgName/old-workflows lacks: id",
    ]);
  });

  it("rejects overlapping patterns across pages, but not shared prefixes", () => {
    const other: RegistryEntry = {
      ...base,
      page: "UN10",
      v1Routes: ["/:orgName/workflows/*"],
      replaces: [],
      toV1: {},
    };
    expect(problemsOf(base, other)).toEqual([
      "UN05 /:orgName/workflows overlaps UN10 /:orgName/workflows/*",
    ]);
    expect(
      problemsOf(base, { ...other, v1Routes: ["/:orgName/workflows/logs"] }),
    ).toEqual([]);
  });

  it("rejects duplicates, empty routes or distributions, and malformed patterns", () => {
    expect(
      problemsOf(base, {
        ...base,
        v1Routes: ["/:orgName/other"],
        replaces: [],
        toV1: {},
      }),
    ).toContain("UN05: declared twice");
    expect(
      problemsOf({
        ...base,
        v1Routes: [],
        replaces: [],
        toV1: {},
        distributions: [],
      }),
    ).toEqual(["UN05: has no v1 routes", "UN05: ships in no distribution"]);
    expect(
      problemsOf({
        ...base,
        v1Routes: ["workflows", "/:orgName/:id?", "/a/*/b"],
        replaces: [],
        toV1: {},
      }),
    ).toEqual([
      "UN05: route workflows must start with /",
      "UN05: route /:orgName/:id? segment ':id?' is not a static name, :param or a final *",
      "UN05: route /a/*/b * is allowed only as the last segment",
    ]);
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
